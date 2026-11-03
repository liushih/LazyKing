"""统一升版本号：一次写入所有需要 version 的插件清单。

用法：python scripts/bump_version.py 1.5.2
唯一来源是 .claude-plugin/plugin.json；Codex、Cursor 清单是各自平台的格式，需要同样的版本号，由本脚本同步。
marketplace.json 不放 version（官方要求插件与市场不要重复设置）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
)

_VERSION_FIELD = re.compile(r'("version"\s*:\s*")([^"]*)(")')
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def current_version(root: Path) -> str:
    text = (Path(root) / MANIFESTS[0]).read_text(encoding="utf-8")
    match = _VERSION_FIELD.search(text)
    if match is None:
        raise ValueError(f"{MANIFESTS[0]} 中没有 version")
    return match.group(2)


def bump(root: Path, version: str) -> list[Path]:
    if not _SEMVER.fullmatch(version or ""):
        raise ValueError(f"版本号必须是 X.Y.Z：{version!r}")
    root = Path(root)
    changed: list[Path] = []
    for rel in MANIFESTS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        new_text, count = _VERSION_FIELD.subn(
            lambda m: f"{m.group(1)}{version}{m.group(3)}", text, count=1
        )
        if count != 1:
            raise ValueError(f"{rel} 中没有 version")
        path.write_text(new_text, encoding="utf-8")
        changed.append(path)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统一升版本号")
    parser.add_argument("version", help="新版本号，如 1.5.2")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    try:
        before = current_version(Path(args.root))
        bump(Path(args.root), args.version)
    except (ValueError, OSError) as exc:
        print(f"[版本] {exc}")
        return 2
    print(f"{before} -> {args.version}")
    for rel in MANIFESTS:
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
