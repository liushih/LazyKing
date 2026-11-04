"""个人配置的命令行入口。"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import yaml  # noqa: E402

from runtime import personal  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_INVALID = 0, 2, 3
ERROR_DRIFT = {"undeclared_variable", "duplicate_declaration", "missing_example"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="个人配置检查与写入")
    parser.add_argument("--project", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check")
    check.add_argument("--capability", choices=personal.CAPABILITIES)
    check.add_argument("--json", action="store_true")

    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("pairs", nargs="+")
    set_cmd.add_argument("--allow-unknown", action="store_true")

    secret = sub.add_parser("set-secret")
    secret.add_argument("key")

    example = sub.add_parser("example")
    example.add_argument("--write", action="store_true")
    return parser


def _has_invalid(report: personal.CheckReport) -> bool:
    return any(item.status == "invalid" for item in report.capabilities.values())


def _check_exit(report: personal.CheckReport, capability: str | None) -> int:
    if _has_invalid(report):
        return EXIT_INVALID
    if capability is not None:
        cap = report.capabilities[capability]
        return EXIT_CONFIG if cap.status == "missing" or cap.drift else EXIT_OK
    errors = [item for item in report.drift if item.kind in ERROR_DRIFT]
    errors.extend(
        item
        for cap in report.capabilities.values()
        for item in cap.drift
        if item.kind in ERROR_DRIFT
    )
    return EXIT_CONFIG if errors else EXIT_OK


def _print_report(report: personal.CheckReport) -> None:
    for name, cap in report.capabilities.items():
        print(f"[{name}] {cap.status}")
        for item in cap.missing:
            label = "个人" if item.target == "personal" else "密钥"
            description = f"：{item.description}" if item.description else ""
            print(f"  缺 {item.key}（{label}）{description}")
        for item in cap.drift:
            print(f"  {item.file}: {item.message}")
    for item in report.drift:
        print(f"{item.file}: {item.message}")


def _cmd_check(args) -> int:
    try:
        report = personal.check(args.project, args.capability)
    except personal.PersonalConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_CONFIG
    if args.json:
        print(json.dumps(personal.report_json(report), ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return _check_exit(report, args.capability)


def _cmd_set(args) -> int:
    values: dict[str, str] = {}
    for pair in args.pairs:
        if "=" not in pair:
            print(f"[参数] 需要 KEY=VALUE：{pair}")
            return EXIT_CONFIG
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            print("[参数] 键不能为空")
            return EXIT_CONFIG
        values[key] = value
    try:
        written = personal.set_value(
            args.project, values, allow_unknown=args.allow_unknown
        )
    except personal.PersonalConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_CONFIG
    print(f"已写入 personal.yaml：{', '.join(written)}")
    return EXIT_OK


def _cmd_secret(args) -> int:
    if sys.stdin.isatty():
        value = getpass.getpass(f"{args.key}: ")
    else:
        value = sys.stdin.readline().strip()
    try:
        personal.set_secret(args.project, args.key, value)
    except personal.PersonalConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_CONFIG
    print(f"已写入 .env：{args.key}")
    return EXIT_OK


def _example_payload(project_id: str) -> dict:
    specs = personal.build_example(project_id)
    return {
        "version": 1,
        "keys": {
            key: {
                "description": spec.description,
                "type": spec.type,
                "default_from": spec.default_from,
            }
            for key, spec in specs.items()
        },
    }


def _print_secret_candidates(project_id: str) -> None:
    for key in sorted(personal.secret_candidates(project_id)):
        print(f"需要补进 .env.example：{key}")


def _cmd_example(args) -> int:
    try:
        if args.write:
            path = personal.write_example(args.project)
            if path is None:
                print("personal.example.yaml 已存在，未覆盖")
            else:
                print(f"已生成 personal.example.yaml：{path}")
        else:
            print(
                yaml.safe_dump(
                    _example_payload(args.project),
                    sort_keys=False,
                    allow_unicode=True,
                )
            )
        _print_secret_candidates(args.project)
    except personal.PersonalConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_CONFIG
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "set":
        return _cmd_set(args)
    if args.cmd == "set-secret":
        return _cmd_secret(args)
    if args.cmd == "example":
        return _cmd_example(args)
    return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
