"""Jenkins 发版的命令行入口。token 只从项目 .env 读取，setup 经 stdin 接收。"""

from __future__ import annotations

import argparse
import sys
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
    return EXIT_OK if hit else EXIT_FAIL


def _status(client, job: str, number: int) -> int:
    status = client.build_status(job, number)
    if status.building:
        label = "BUILDING"
    else:
        label = status.result or "UNKNOWN"
    print(f"[{label}] {job} #{number} {status.url}")
    return EXIT_OK if label in ("SUCCESS", "BUILDING") else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
