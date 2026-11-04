"""由改动文件推断要构建的模块，并检查分支是否已推送。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import ModuleSpec


class ModulesError(Exception):
    pass


def _norm(path: str) -> str:
    path = path.replace("\\", "/")
    return path[2:] if path.startswith("./") else path


def _match_len(file: str, prefix: str) -> int:
    base = prefix.replace("\\", "/").rstrip("/")
    if file == base or file.startswith(base + "/"):
        return len(base)
    return -1


def infer_modules(
    changed: list[str], modules: list[ModuleSpec]
) -> tuple[list[ModuleSpec], list[str]]:
    hit_names: set[str] = set()
    unmapped: list[str] = []
    for raw in changed:
        file = _norm(raw)
        best_len, best = -1, None
        for module in modules:
            for prefix in module.paths:
                length = _match_len(file, prefix)
                if length > best_len:
                    best_len, best = length, module
        if best is None:
            unmapped.append(raw)
        else:
            hit_names.add(best.name)
    return [m for m in modules if m.name in hit_names], unmapped


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ModulesError(detail[-1] if detail else f"git {args[0]} 失败")
    return result.stdout.strip()


def changed_files(repo: Path, baseline: str) -> list[str]:
    try:
        base = _git(repo, "merge-base", baseline, "HEAD")
    except ModulesError as exc:
        raise ModulesError(f"无法与基线 {baseline} 比较：{exc}") from None
    out = _git(repo, "diff", "--name-only", base, "HEAD")
    return [line for line in out.splitlines() if line.strip()]


def unpushed_commits(repo: Path, branch: str) -> int | None:
    if not _git(repo, "rev-parse", "--verify", "-q", f"origin/{branch}", check=False):
        return None
    return int(_git(repo, "rev-list", "--count", f"origin/{branch}..HEAD"))


def current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
