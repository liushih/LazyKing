"""把工具包同步进业务仓库：按白名单复制到 data-tools/ 并写入 VERSION。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"

TOOLKIT_ITEMS: tuple[str, ...] = (
    "skills",
    "runtime",
    "scripts",
    "requirements.txt",
    "bootstrap.ps1",
    "update.ps1",
    "LICENSE",
)

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")


@dataclass
class SyncResult:
    copied: list[Path] = field(default_factory=list)
    rendered: list[Path] = field(default_factory=list)
    preserved: list[Path] = field(default_factory=list)


def copy_toolkit(source_root: Path, project_dir: Path) -> list[Path]:
    """把白名单条目从 source_root 复制到 project_dir/data-tools，返回复制后的路径。"""
    dest_root = project_dir / "data-tools"
    copied: list[Path] = []
    for item in TOOLKIT_ITEMS:
        src = source_root / item
        if not src.exists():
            continue
        dest = dest_root / item
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=IGNORE_PATTERNS)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def _source_commit(source_root: Path) -> str:
    # 只认 source_root 自身是仓库根的情况，避免误取上层无关仓库的 commit。
    if not (source_root / ".git").exists():
        return "unknown"
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def write_version(source_root: Path, project_dir: Path, source_url: str = DEFAULT_SOURCE) -> Path:
    """读取 plugin.json 的 version，写入 data-tools/VERSION，返回该文件路径。"""
    plugin = json.loads(
        (source_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    data = {
        "version": plugin["version"],
        "source_commit": _source_commit(source_root),
        "synced_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source_url,
    }
    dest = project_dir / "data-tools" / "VERSION"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest