"""Jenkins 发版的命令行入口。token 只从项目 .env 读取，setup 经 stdin 接收。"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime.jenkins.client import JenkinsClient, JenkinsError  # noqa: E402
from runtime.jenkins.config import (  # noqa: E402
    JenkinsConfigError,
    load_jenkins_config,
    read_token,
    save_credentials,
)
from runtime.jenkins.modules import (  # noqa: E402
    ModulesError,
    changed_files,
    current_branch,
    infer_modules,
    uncommitted_files,
    unpushed_commits,
)

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2

MAX_UNMAPPED_SHOWN = 20


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jenkins 发版")
    parser.add_argument("--project", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)

    setup = sub.add_parser("setup", help="保存地址与账号；token 从 stdin 读取")
    setup.add_argument("--base-url", required=True)
    setup.add_argument("--user", required=True)

    discover = sub.add_parser("discover", help="列出任务及其参数")
    discover.add_argument("--filter", default="")

    modules = sub.add_parser("modules", help="按改动推断要构建的模块")
    modules.add_argument("--repo", default=".")

    status = sub.add_parser("status", help="查询某次构建")
    status.add_argument("--job", required=True)
    status.add_argument("--number", required=True, type=int)

    build = sub.add_parser("build", help="触发构建")
    build.add_argument("--env", required=True)
    build.add_argument("--module", action="append", default=[])
    build.add_argument("--branch")
    build.add_argument("--repo", default=".")
    build.add_argument("--sequential", action="store_true", help="前一个成功再触发下一个")
    build.add_argument("--no-wait", action="store_true", help="只触发，不等结果")
    build.add_argument("--dry-run", action="store_true", help="只回显计划，不触发")
    return parser


def _default_client(cfg, token: str) -> JenkinsClient:
    return JenkinsClient(cfg.base_url, cfg.user, token)


def main(argv: list[str] | None = None, client_fn=None, stdin=None) -> int:
    args = _build_parser().parse_args(argv)
    client_fn = client_fn or _default_client
    stdin = stdin if stdin is not None else sys.stdin

    try:
        if args.cmd == "setup":
            return _setup(args, client_fn, stdin)

        cfg = load_jenkins_config(args.project)
        if args.cmd == "modules":
            return _modules(cfg, Path(args.repo))

        client = client_fn(cfg, read_token(args.project, cfg.token_key))
        if args.cmd == "discover":
            return _discover(client, args.filter)
        if args.cmd == "status":
            return _status(client, args.job, args.number)
        if args.cmd == "build":
            return _build(cfg, client, args)
    except JenkinsConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_USAGE
    except JenkinsError as exc:
        print(f"[{exc.kind}] {exc}")
        return EXIT_FAIL
    except ModulesError as exc:
        print(f"[git] {exc}")
        return EXIT_FAIL

    return EXIT_USAGE


def _setup(args, client_fn, stdin) -> int:
    token = stdin.read().strip()
    if not token:
        print("[配置] stdin 中没有 token：请通过标准输入传入，不要放在命令行参数里")
        return EXIT_USAGE

    save_credentials(args.project, args.base_url, args.user, token)
    cfg = load_jenkins_config(args.project)
    client = client_fn(cfg, token)
    try:
        who = client.whoami()
    except JenkinsError as exc:
        print(f"已保存配置，但验证失败：[{exc.kind}] {exc}")
        return EXIT_FAIL
    print(f"已保存配置与 {cfg.token_key}；已验证：登录为 {who}")
    return EXIT_OK


def _discover(client, keyword: str) -> int:
    needle = keyword.lower()
    for job in client.list_jobs():
        if needle and needle not in job.lower():
            continue
        print(job)
        try:
            params = client.job_params(job)
        except JenkinsError as exc:
            print(f"  （无法读取参数：{exc}）")
            continue
        for p in params:
            default = "无" if p.default is None else p.default
            line = f"  - {p.name} ({p.type}) 默认={default}"
            if p.choices:
                line += f" 可选={','.join(p.choices)}"
            print(line)
    return EXIT_OK


def _modules(cfg, repo: Path) -> int:
    branch = current_branch(repo)
    changed = changed_files(repo, cfg.baseline)
    hit, unmapped = infer_modules(changed, cfg.modules)
    pushed = unpushed_commits(repo, branch)

    print(f"分支：{branch}")
    print(f"基线：{cfg.baseline}")
    print(f"命中模块：{', '.join(m.name for m in hit)}" if hit else "无命中模块")
    if unmapped:
        print(f"未映射文件（{len(unmapped)}）：")
        for path in unmapped[:MAX_UNMAPPED_SHOWN]:
            print(f"  {path}")
        if len(unmapped) > MAX_UNMAPPED_SHOWN:
            print(f"  另有 {len(unmapped) - MAX_UNMAPPED_SHOWN} 个")
    print("未推送提交：远端无该分支" if pushed is None else f"未推送提交：{pushed}")
    _print_uncommitted(repo)
    return EXIT_OK if hit else EXIT_FAIL


def _print_uncommitted(repo: Path) -> None:
    pending = uncommitted_files(repo)
    if not pending:
        return
    print(f"未提交的改动（{len(pending)}，不会被构建，也未计入模块推断）：")
    for path in pending[:MAX_UNMAPPED_SHOWN]:
        print(f"  {path}")
    if len(pending) > MAX_UNMAPPED_SHOWN:
        print(f"  另有 {len(pending) - MAX_UNMAPPED_SHOWN} 个")


def _status(client, job: str, number: int) -> int:
    status = client.build_status(job, number)
    if status.building:
        label = "BUILDING"
    else:
        label = status.result or "UNKNOWN"
    print(f"[{label}] {job} #{number} {status.url}")
    return EXIT_OK if label in ("SUCCESS", "BUILDING") else EXIT_FAIL


@dataclass
class PlannedBuild:
    module: str
    job: str
    params: dict[str, str] | None


def _select_modules(cfg, args, repo: Path):
    if args.module:
        by_name = {m.name: m for m in cfg.modules}
        unknown = [name for name in args.module if name not in by_name]
        if unknown:
            raise JenkinsConfigError(
                f"未知模块：{', '.join(unknown)}；可用：{', '.join(by_name) or '（无）'}"
            )
        wanted = set(args.module)
        return [m for m in cfg.modules if m.name in wanted]

    hit, unmapped = infer_modules(changed_files(repo, cfg.baseline), cfg.modules)
    if unmapped:
        print(f"提示：{len(unmapped)} 个改动文件未映射到任何模块，不会构建")
    _print_uncommitted(repo)
    if not hit:
        raise JenkinsConfigError("没有可构建的模块：改动未命中任何模块，请用 --module 指定")
    return hit


def _preflight(client, modules, env: str, branch: str) -> list[PlannedBuild]:
    """先于任何触发请求，对所有选中的模块整体检查；有任何问题就一个都不触发。"""
    problems: list[str] = []
    jobs: dict[str, str] = {}
    for module in modules:
        job = module.jobs.get(env)
        if job is None:
            problems.append(
                f"模块 {module.name} 没有环境 {env} 的任务（已配置：{', '.join(module.jobs)}）"
            )
        else:
            jobs[module.name] = job
    if problems:
        raise JenkinsConfigError("\n".join(problems))

    planned: list[PlannedBuild] = []
    for module in modules:
        job = jobs[module.name]
        given = {k: v.replace("{branch}", branch) for k, v in module.params.items()}
        declared = client.job_params(job)
        names = {p.name for p in declared}
        unknown = sorted(set(given) - names)
        missing = [p.name for p in declared if p.required and p.name not in given]
        if unknown:
            problems.append(f"任务 {job} 不认识参数 {', '.join(unknown)}（模块 {module.name}）")
        if missing:
            problems.append(f"任务 {job} 缺少必填参数 {', '.join(missing)}（模块 {module.name}）")
        planned.append(PlannedBuild(module.name, job, given if declared else None))
    if problems:
        raise JenkinsConfigError("\n".join(problems))
    return planned


def _describe(item: PlannedBuild) -> str:
    params = ",".join(f"{k}={v}" for k, v in (item.params or {}).items()) or "无"
    return f"{item.module} → {item.job} 参数={params}"


def _build(cfg, client, args) -> int:
    repo = Path(args.repo)
    modules = _select_modules(cfg, args, repo)
    branch = args.branch or current_branch(repo)
    planned = _preflight(client, modules, args.env, branch)

    if args.dry_run:
        print(f"分支：{branch}  环境：{args.env}  Jenkins：{cfg.base_url}")
        for item in planned:
            print(_describe(item))
        return EXIT_OK

    timeout_s = cfg.build_timeout_minutes * 60
    ok = True

    def finish(item: PlannedBuild, queue_url: str) -> bool:
        try:
            number = client.wait_for_build(queue_url, timeout_s)
            status = client.wait_finished(item.job, number, timeout_s)
        except JenkinsError as exc:
            print(f"[{exc.kind}] {item.module} → {item.job} {exc} {exc.url or ''}".rstrip())
            return False
        result = status.result or "UNKNOWN"
        print(f"[{result}] {item.module} → {item.job} #{status.number} {status.url}")
        if result != "SUCCESS":
            try:
                print("--- 控制台末尾 ---")
                print(client.console_tail(item.job, status.number))
            except JenkinsError as exc:
                print(f"（读取控制台失败：{exc}）")
        return result == "SUCCESS"

    def trigger(item: PlannedBuild) -> str | None:
        try:
            return client.trigger(item.job, item.params)
        except JenkinsError as exc:
            print(f"[{exc.kind}] {item.module} → {item.job} {exc}")
            return None

    if args.sequential:
        for index, item in enumerate(planned):
            queue_url = trigger(item)
            if queue_url is None or (not args.no_wait and not finish(item, queue_url)):
                ok = False
                for rest in planned[index + 1:]:
                    print(f"[未触发] {rest.module} → {rest.job}")
                break
            if args.no_wait:
                print(f"[已触发] {item.module} → {item.job} 队列 {queue_url}")
        return EXIT_OK if ok else EXIT_FAIL

    queued: list[tuple[PlannedBuild, str]] = []
    for item in planned:
        queue_url = trigger(item)
        if queue_url is None:
            ok = False
        else:
            queued.append((item, queue_url))
    for item, queue_url in queued:
        if args.no_wait:
            print(f"[已触发] {item.module} → {item.job} 队列 {queue_url}")
        elif not finish(item, queue_url):
            ok = False
    return EXIT_OK if ok else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
