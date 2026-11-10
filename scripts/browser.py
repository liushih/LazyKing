"""浏览器测试命令行。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime.browser import report as report_mod
from runtime.browser.config import (
    BrowserConfigError,
    FlowNotFoundError,
    find_unresolved,
    list_flows,
    load_browser_config,
    load_flow,
    profile_path,
    resolve_variables,
)
from runtime.browser.diagnose import PageCollector, capture
from runtime.browser.driver import (
    BrowserEnvError,
    clear_profile_cache,
    close,
    find_chrome,
    launch,
    profile_in_use,
    resident_profiles,
    session_lost,
    stop_resident,
)
from runtime.browser.flow import FlowRunError, ensure_login, run_flow
from runtime.browser.report import artifacts_dir, write_report
from runtime.browser.watch import WatchController
from runtime.config import ConfigError, data_home, load_values, project_dir, resolve_project, substitute

PASS = 0
FLOW_FAIL = 1
CONFIG_ERROR = 2
FLOW_NOT_FOUND = 3
ENV_ERROR = 4

_RUNTIME_VARS = {"BASE_URL", "username", "password"}


def _missing_browser_variables(project: str) -> list[str]:
    browser_yaml = project_dir(project) / "browser" / "browser.yaml"
    try:
        text = browser_yaml.read_text(encoding="utf-8")
    except OSError:
        text = ""
    referenced = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text)) - _RUNTIME_VARS
    values = {**os.environ, **load_values(project_dir(project))}
    return sorted(name for name in referenced if name not in values)
_PROBE_JS = """
() => {
  const text = (el) => (el.innerText || '').trim();
  return {
    buttons: [...document.querySelectorAll('button')].slice(0, 50).map((el) => ({
      text: text(el),
      testid: el.getAttribute('data-testid'),
      role: el.getAttribute('role')
    })),
    inputs: [...document.querySelectorAll('input')].slice(0, 50).map((el) => ({
      placeholder: el.getAttribute('placeholder'),
      testid: el.getAttribute('data-testid')
    })),
    rows: [...document.querySelectorAll('table tbody tr')].slice(0, 50).map((el) => ({
      text: text(el)
    }))
  };
}
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="browser.py", description="浏览器测试")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="检查浏览器环境")
    doctor.add_argument("--project")

    list_cmd = sub.add_parser("list", help="列出已沉淀流程")
    list_cmd.add_argument("--project")
    list_cmd.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="执行流程")
    run.add_argument("--project")
    run.add_argument("--flow", required=True)
    run.add_argument("--env")
    run.add_argument("--var", action="append", default=[])
    run.add_argument("--headless", action="store_true")
    run.add_argument("--headed", action="store_true", help="显示窗口（一次性启动，会先关掉常驻浏览器）")
    run.add_argument("--watch", action="store_true", help="观看模式：显示窗口并慢放，页面右上角有暂停/调速控制条")
    run.add_argument("--trace", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--profile")

    probe = sub.add_parser("probe", help="探索页面")
    probe.add_argument("--project")
    probe.add_argument("--url", required=True)
    probe.add_argument("--label", default="probe")
    probe.add_argument("--env")
    probe.add_argument("--headless", action="store_true")
    probe.add_argument("--headed", action="store_true")
    probe.add_argument("--profile")

    stop = sub.add_parser("stop", help="关闭常驻浏览器")
    stop.add_argument("--project")
    stop.add_argument("--env")
    stop.add_argument("--profile")
    stop.add_argument("--all", action="store_true", help="关闭本机所有项目的常驻浏览器")

    clean = sub.add_parser("clean", help="清理运行产物与 profile 缓存")
    clean.add_argument("--project")
    clean.add_argument("--env")
    clean.add_argument("--profile")
    clean.add_argument("--all", action="store_true", help="清理本机所有 profile 缓存")

    diagnose = sub.add_parser("diagnose", help="查看最近诊断包")
    diagnose.add_argument("--project")
    diagnose.add_argument("--last", action="store_true")
    return parser


def _parse_vars(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--var 需要 K=V：{item}")
        key, value = item.split("=", 1)
        if not key.strip():
            raise ValueError(f"--var 的键不能为空：{item}")
        result[key.strip()] = value
    return result


def _chrome_path() -> str | None:
    return find_chrome()


def _launch_options(args: argparse.Namespace, cfg: object) -> dict:
    """常驻（无头、不弹窗）是默认；--headed / --watch 或 resident: false 回到一次性启动。"""
    visible = bool(args.headed or getattr(args, "watch", False))
    resident = bool(cfg.resident) and not visible
    headless = False if visible else bool(args.headless or cfg.headless)
    return {"headless": headless, "resident": resident}


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def cmd_doctor(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    try:
        cfg = load_browser_config(project)
    except BrowserConfigError as exc:
        print(f"[配置] {exc}")
        return CONFIG_ERROR

    checks: list[tuple[str, bool, str]] = [
        ("Python 3.11+", sys.version_info >= (3, 11), sys.version.split()[0])
    ]
    try:
        from importlib.metadata import version

        checks.append(("Playwright", True, version("playwright")))
    except Exception:
        checks.append(("Playwright", False, "未安装"))
    chrome = _chrome_path()
    checks.append(("Chrome", bool(chrome), chrome or "未找到"))
    profile = profile_path(cfg, cfg.default_env)
    checks.append(("profile 可写", _writable(profile), str(profile)))

    try:
        missing = _missing_browser_variables(project)
        checks.append(("变量齐全", not missing, ", ".join(missing) if missing else "OK"))
    except ConfigError as exc:
        checks.append(
            ("变量齐全", False, f"个人配置缺失或非法，运行 project-setup：{exc}")
        )

    ok = True
    for name, passed, detail in checks:
        print(f"[{'OK' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed
    return PASS if ok else ENV_ERROR


def cmd_list(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    flows = list_flows(project)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "flow": flow.name,
                        "description": flow.description,
                        "env": flow.env,
                        "vars": [
                            name for name, var_def in flow.vars.items() if var_def.required
                        ],
                    }
                    for flow in flows
                ],
                ensure_ascii=False,
            )
        )
        return PASS

    if not flows:
        print("没有已沉淀流程")
        return PASS
    for flow in flows:
        required = ",".join(name for name, var_def in flow.vars.items() if var_def.required) or "-"
        print(f"{flow.name}\t{flow.description or '-'}\tenv={flow.env or '-'}\tvars={required}")
    return PASS


def cmd_run(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    cfg = load_browser_config(project)
    flow = load_flow(project, args.flow)
    env_name = args.env or flow.env or cfg.default_env
    if env_name not in cfg.envs:
        raise BrowserConfigError(f"未知环境：{env_name}")
    try:
        cli_vars = _parse_vars(args.var)
    except ValueError as exc:
        print(f"[参数] {exc}")
        return CONFIG_ERROR
    variables = resolve_variables(cfg, flow, env_name, cli_vars)
    unresolved = find_unresolved(flow, variables)
    if unresolved:
        raise BrowserConfigError(f"流程引用了未定义的变量：{', '.join(unresolved)}")
    profile = profile_path(cfg, env_name, Path(args.profile) if args.profile else None)

    report_mod.cleanup(project)
    collector = PageCollector()
    session = None
    result = None
    artifacts = None
    trace_path = None
    browser_lost = False
    watch = None
    try:
        session = launch(
            profile=profile,
            tracing=args.trace,
            **_launch_options(args, cfg),
        )
        if args.watch:
            watch = WatchController(session.page)
            watch.attach()
            if not args.json:
                print("[观看] 已打开浏览器窗口：页面右上角可暂停/继续和调速")
        collector.attach(session.page)
        if cfg.login is not None:
            try:
                ensure_login(
                    session.page,
                    cfg.login,
                    variables=variables,
                    project_dir=project_dir(project),
                    timeout_ms=cfg.timeout_ms,
                    pacer=watch,
                )
            except FlowRunError:
                raise
            except Exception as exc:
                if session_lost(session):
                    raise FlowRunError("测试浏览器已被关闭，登录中断") from exc
                raise
        result = run_flow(
            session.page,
            flow,
            env_name,
            variables,
            project_dir(project),
            timeout_ms=cfg.timeout_ms,
            api_watch=cfg.api_watch,
            pacer=watch,
        )
        if result.result == "fail":
            if session_lost(session):
                # 浏览器被手动关了，后面的失败都是连带的，不是流程本身的问题，也取不到有用的诊断。
                browser_lost = True
            else:
                if watch is not None:
                    watch.hide()
                try:
                    artifacts = capture(session.page, project, flow, result, collector)
                    result.artifacts = str(artifacts)
                except Exception as exc:
                    print(f"[诊断] 生成失败：{exc}")
    finally:
        if session is not None:
            if args.trace:
                try:
                    trace_path = report_mod.traces_dir(project) / f"{flow.name}-{report_mod.timestamp()}.zip"
                    trace_path.parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    trace_path = None
            close(session, trace_path)
        if trace_path is not None:
            if artifacts and trace_path.exists():
                try:
                    shutil.copyfile(trace_path, Path(artifacts) / "trace.zip")
                except OSError:
                    pass
            # trace 只在失败时随诊断包保留；通过、异常或复制失败都不留原始压缩包。
            try:
                trace_path.unlink()
            except OSError:
                pass

    report_path = write_report(project, result)
    if result.result == "pass":
        # 流程已经修好，之前的失败诊断包对这次任务没用了，立即删掉。
        report_mod.clear_artifacts(project, flow.name)
    if browser_lost:
        print(
            f"[环境] 测试浏览器在运行 {result.flow} 的过程中被关闭，本次结果无效，请重跑；"
            f"报告 {report_path}"
        )
        return ENV_ERROR
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False))
    elif result.result == "pass":
        print(f"{result.flow} 通过：{len(result.steps)} 步，{result.duration_ms}ms；报告 {report_path}")
    else:
        failure = result.failure
        where = f"{failure.step_index}. {failure.step_name}" if failure else "未知"
        print(f"{result.flow} 失败：{where}；诊断 {result.artifacts or '-'}；报告 {report_path}")
    return PASS if result.result == "pass" else FLOW_FAIL


def cmd_probe(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    cfg = load_browser_config(project)
    env_name = args.env or cfg.default_env
    if env_name not in cfg.envs:
        raise BrowserConfigError(f"未知环境：{env_name}")
    env = cfg.envs[env_name]
    variables = {**os.environ, **env.values, "BASE_URL": env.base_url}
    try:
        url = str(substitute(args.url, variables))
    except Exception as exc:
        raise BrowserConfigError(f"URL 变量解析失败：{exc}") from exc
    profile = profile_path(cfg, env_name, Path(args.profile) if args.profile else None)

    report_mod.cleanup(project)
    out = report_mod.probes_dir(project) / f"{report_mod.timestamp()}-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    collector = PageCollector()
    session = launch(profile=profile, **_launch_options(args, cfg))
    try:
        collector.attach(session.page)
        if cfg.login is not None:
            ensure_login(
                session.page,
                cfg.login,
                variables=variables,
                project_dir=project_dir(project),
                timeout_ms=cfg.timeout_ms,
            )
        session.page.goto(url, wait_until="domcontentloaded")
        try:
            session.page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        elements = session.page.evaluate(_PROBE_JS)
        try:
            session.page.screenshot(path=str(out / "page.png"), full_page=True)
        except Exception:
            pass
        try:
            (out / "page.html").write_text(session.page.content(), encoding="utf-8")
        except Exception:
            pass
        (out / "elements.json").write_text(
            json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "requests.json").write_text(
            json.dumps(collector.requests, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "console.log").write_text("\n".join(collector.console), encoding="utf-8")
        (out / "probe.md").write_text(_probe_markdown(session.page, elements), encoding="utf-8")
    finally:
        close(session)

    print(f"探索快照：{out}")
    return PASS


def _probe_markdown(page: object, elements: dict) -> str:
    try:
        url = page.url
        title = page.title()
    except Exception:
        url = "unknown"
        title = "unknown"
    lines = [
        "# 页面探索快照",
        "",
        f"- URL：{url}",
        f"- 标题：{title}",
        f"- 按钮：{len(elements.get('buttons', []))}",
        f"- 输入框：{len(elements.get('inputs', []))}",
        f"- 表格行：{len(elements.get('rows', []))}",
        "",
        "## 按钮",
    ]
    for button in elements.get("buttons", [])[:20]:
        lines.append(
            f"- text={button.get('text')!r} testid={button.get('testid')!r} role={button.get('role')!r}"
        )
    lines.append("")
    return "\n".join(lines)


def cmd_stop(args: argparse.Namespace) -> int:
    if args.all:
        profiles = resident_profiles(data_home() / "browser" / "profiles")
    else:
        project = resolve_project(args.project)
        cfg = load_browser_config(project)
        env_name = args.env or cfg.default_env
        if env_name not in cfg.envs:
            raise BrowserConfigError(f"未知环境：{env_name}")
        profiles = [profile_path(cfg, env_name, Path(args.profile) if args.profile else None)]

    stopped = 0
    for profile in profiles:
        if stop_resident(profile):
            stopped += 1
            print(f"已关闭常驻浏览器（缓存已清理）：{profile}")
    if not stopped:
        print("没有运行中的常驻浏览器")
    return PASS


def _all_profiles() -> list[Path]:
    """<DATA_HOME>/browser/profiles 下的 profile 目录（支持 <项目>/<环境> 与直接平铺两种）。"""
    root = data_home() / "browser" / "profiles"
    if not root.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "Local State").exists() or (child / "Default").is_dir():
            found.append(child)
            continue
        for nested in sorted(child.iterdir()):
            if nested.is_dir() and ((nested / "Local State").exists() or (nested / "Default").is_dir()):
                found.append(nested)
    return found


def _mb(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


def cmd_clean(args: argparse.Namespace) -> int:
    counts = report_mod.clean_all(args.project)
    if args.all:
        profiles = _all_profiles()
    else:
        project = resolve_project(args.project)
        cfg = load_browser_config(project)
        env_name = args.env or cfg.default_env
        if env_name not in cfg.envs:
            raise BrowserConfigError(f"未知环境：{env_name}")
        profiles = [profile_path(cfg, env_name, Path(args.profile) if args.profile else None)]

    freed = 0
    skipped = 0
    for profile in profiles:
        if profile_in_use(profile):
            skipped += 1
            continue
        freed += clear_profile_cache(profile)

    removed = sum(counts.values())
    print(
        f"运行产物：清理 {removed} 项"
        f"（报告 {counts['reports']}，诊断包 {counts['artifacts']}，"
        f"探索快照 {counts['probes']}，trace {counts['traces']}）"
    )
    if profiles:
        note = f"；{skipped} 个正在使用，已跳过" if skipped else ""
        print(f"profile 缓存：释放 {_mb(freed)}{note}")
    return PASS


def cmd_diagnose(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    directory = artifacts_dir(project)
    if not directory.is_dir():
        print("没有诊断包")
        return CONFIG_ERROR
    latest = report_mod.latest_entry(directory)
    if latest is None or not latest.is_dir():
        print("没有诊断包")
        return CONFIG_ERROR
    diagnosis = latest / "diagnosis.md"
    if not diagnosis.exists():
        print(f"诊断包缺少 diagnosis.md：{latest}")
        return CONFIG_ERROR
    print(diagnosis.read_text(encoding="utf-8"))
    print(f"\n诊断包：{latest}")
    return PASS


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return cmd_doctor(args)
        if args.command == "list":
            return cmd_list(args)
        if args.command == "run":
            return cmd_run(args)
        if args.command == "probe":
            return cmd_probe(args)
        if args.command == "stop":
            return cmd_stop(args)
        if args.command == "clean":
            return cmd_clean(args)
        return cmd_diagnose(args)
    except FlowNotFoundError as exc:
        print(f"[流程] {exc}")
        return FLOW_NOT_FOUND
    except BrowserConfigError as exc:
        print(f"[配置] {exc}")
        return CONFIG_ERROR
    except BrowserEnvError as exc:
        print(f"[环境] {exc}")
        return ENV_ERROR
    except FlowRunError as exc:
        print(f"[环境] {exc}")
        return ENV_ERROR


if __name__ == "__main__":
    sys.exit(main())
