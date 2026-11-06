"""把业务仓库里团队共享的文件暂存进 git。不提交、不推送，也不使用 git add -f。"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_FILES = {
    "adapter.yaml",
    "pitfalls.md",
    "report.yaml",
    "git_hosts.yaml",
    "jenkins.yaml",
    "personal.example.yaml",
    ".env.example",
}

PRIVATE_NAMES = {
    ".env",
    "personal.yaml",
    "ledger.csv",
    "state.json",
}


class TrackError(Exception):
    """路径不能自动暂存时抛出。校验失败不会改动暂存区。"""


@dataclass
class TrackResult:
    staged: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _require_repo(project_dir: Path) -> Path:
    root = Path(project_dir).resolve()
    probe = _git(root, "rev-parse", "--show-toplevel")
    if probe.returncode != 0:
        raise TrackError(f"不是 git 仓库：{project_dir}")
    toplevel = Path(probe.stdout.strip()).resolve()
    if os.path.normcase(str(toplevel)) != os.path.normcase(str(root)):
        raise TrackError(f"请传入业务仓库根目录：{toplevel}")
    return root


def _private_name(name: str) -> bool:
    if name in PRIVATE_NAMES or name.endswith((".pyc", ".log")):
        return True
    return name.startswith(".token") or ".token" in name


def is_shareable(rel: Path) -> bool:
    """团队可复用的项目文件才返回 True。凭据、个人值和运行产物一律 False。"""
    parts = rel.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if _private_name(rel.name) or "__pycache__" in parts:
        return False
    if parts[0] != ".data-tools" or len(parts) < 4:
        return False
    if parts[1] == "templates":
        return True
    if parts[1] != "projects":
        return False
    rest = parts[3:]
    if rest in {("browser", "browser.yaml"), ("browser", "pitfalls.md"), ("browser", "controls.md")}:
        return True
    if (
        len(rest) == 3
        and rest[0] == "browser"
        and rest[1] == "flows"
        and rest[2].endswith((".yaml", ".yml"))
    ):
        return True
    if len(rest) == 1 and rest[0] in PROJECT_FILES:
        return True
    return bool(rest) and rest[0] == "scripts" and len(rest) >= 2


def _relative(root: Path, raw: str) -> str:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise TrackError(f"路径不在仓库内：{raw}") from exc
    if not resolved.is_file():
        raise TrackError(f"文件不存在：{raw}")
    text = rel.as_posix()
    if not is_shareable(Path(text)):
        raise TrackError(f"该路径不自动纳入版本库：{text}")
    return text


def _ignored(root: Path, rel: str) -> bool:
    probe = _git(root, "check-ignore", "-q", "--", rel)
    if probe.returncode in (0, 1):
        return probe.returncode == 0
    detail = (probe.stderr or probe.stdout).strip() or "无法判断 gitignore"
    raise TrackError(detail)


def _dirty(root: Path, rel: str) -> bool:
    probe = _git(root, "status", "--porcelain", "--", rel)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip() or "无法读取 git 状态"
        raise TrackError(detail)
    return bool(probe.stdout.strip())


def track_shared(project_dir: Path, paths: list[str]) -> TrackResult:
    """校验通过后暂存。有任一路径非法时全部不暂存。"""
    if not paths:
        raise TrackError("没有要暂存的文件")
    root = _require_repo(project_dir)
    rels = [_relative(root, raw) for raw in paths]
    result = TrackResult()
    to_add: list[str] = []
    for rel in rels:
        if _ignored(root, rel):
            result.ignored.append(rel)
        elif not _dirty(root, rel):
            result.unchanged.append(rel)
        else:
            to_add.append(rel)
    if to_add:
        added = _git(root, "add", "--", *to_add)
        if added.returncode != 0:
            detail = (added.stderr or added.stdout).strip() or "git add 失败"
            raise TrackError(detail)
        result.staged.extend(to_add)
    return result
