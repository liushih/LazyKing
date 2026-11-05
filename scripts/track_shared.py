"""把团队共享文件暂存进业务仓库。不提交、不推送。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.track_shared import TrackError, track_shared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="暂存团队共享文件，不提交、不推送")
    parser.add_argument("--project-dir", type=Path, required=True, help="业务仓库根目录")
    parser.add_argument("paths", nargs="+", help="刚写或刚改的共享文件")
    args = parser.parse_args(argv)
    try:
        result = track_shared(args.project_dir, args.paths)
    except TrackError as exc:
        print(exc, file=sys.stderr)
        return 1
    for rel in result.staged:
        print(f"已暂存 {rel}")
    for rel in result.unchanged:
        print(f"已在版本库中 {rel}")
    for rel in result.ignored:
        print(f"被 gitignore 跳过 {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
