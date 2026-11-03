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
from runtime.browser.driver import BrowserEnvError, close, launch
from runtime.browser.flow import FlowRunError, ensure_login, run_flow
from runtime.browser.report import artifacts_dir, write_report
from runtime.config import data_home, load_env, project_dir, resolve_project, substitute

PASS = 0
FLOW_FAIL = 1
CONFIG_ERROR = 2
FLOW_NOT_FOUND = 3
ENV_ERROR = 4

_RUNTIME_VARS = {"BASE_URL", "username", "password"}
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
    run.add_argument("--trace", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--profile")

    probe = sub.add_parser("probe", help="探索页面")
    probe.add_argument("--project")
    probe.add_argument("--url", required=True)
    probe.add_argument("--label", default="probe")
    probe.add_argument("--env")
    probe.add_argument("--headless", action="store_true")
    probe.add_argument("--profile")

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
    candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


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

    browser_yaml = project_dir(project) / "browser" / "browser.yaml"
    try:
        text = browser_yaml.read_text(encoding="utf-8")
    except OSError:
        text = ""
    referenced = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text)) - _RUNTIME_VARS
    dotenv = load_env(project_dir(project) / ".env")
    missing = sorted(name for name in referenced if name not in dotenv and name not in os.environ)
    checks.append(("变量齐全", not missing, ", ".join(missing) if missing else "OK"))

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

    collector = PageCollector()
    session = None
    result = None
    artifacts = None
    trace_path = None
    try:
        session = launch(
            headless=bool(args.headless or cfg.headless),
            profile=profile,
            tracing=args.trace,
        )
        collector.attach(session.page)
        if cfg.login is not None:
            ensure_login(
                session.page,
                cfg.login,
                variables=variables,
                project_dir=project_dir(project),
                timeout_ms=cfg.timeout_ms,
            )
        result = run_flow(
            session.page,
            flow,
            env_name,
            variables,
            project_dir(project),
            timeout_ms=cfg.timeout_ms,
        )
        if result.result == "fail":
            try:
                artifacts = capture(session.page, project, flow, result, collector)
                result.artifacts = str(artifacts)
            except Exception as exc:
                print(f"[诊断] 生成失败：{exc}")
    finally:
        if session is not None:
            if args.trace:
                try:
                    trace_path = data_home() / "browser" / "traces" / f"{flow.name}-{report_mod.timestamp()}.zip"
                    trace_path.parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    trace_path = None
            close(session, trace_path)

    if args.trace and trace_path and artifacts and trace_path.exists():
        try:
            shutil.copyfile(trace_path, Path(artifacts) / "trace.zip")
        except OSError:
            pass

    report_path = write_report(project, result)
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

    out = data_home() / "browser" / "probes" / f"{report_mod.timestamp()}-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    collector = PageCollector()
    session = launch(headless=bool(args.headless or cfg.headless), profile=profile)
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

    report_mod.prune(out.parent, 20)
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
