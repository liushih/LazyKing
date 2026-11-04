"""浏览器运行报告。"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from runtime.config import data_home

from .flow import FlowResult

KEEP = 20
ARTIFACT_KEEP = 10
ARTIFACT_MAX_AGE = 7 * 24 * 60 * 60
PROBE_KEEP = 10
PROBE_MAX_AGE = 7 * 24 * 60 * 60
TRACE_KEEP = 3
TRACE_MAX_AGE = 3 * 24 * 60 * 60


def timestamp() -> str:
    now = datetime.now()
    return f"{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}"


def browser_dir() -> Path:
    return data_home() / "browser"


def reports_dir(project_id: str) -> Path:
    return browser_dir() / "reports"


def artifacts_dir(project_id: str) -> Path:
    return browser_dir() / "artifacts"


def probes_dir(project_id: str) -> Path:
    return browser_dir() / "probes"


def traces_dir(project_id: str) -> Path:
    return browser_dir() / "traces"


def write_report(project_id: str, result: FlowResult) -> Path:
    directory = reports_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{result.flow}-{timestamp()}"
    path = directory / f"{stem}.json"
    index = 2
    while path.exists():
        path = directory / f"{stem}-{index}.json"
        index += 1
    from .diagnose import scrub_text

    path.write_text(
        scrub_text(json.dumps(asdict(result), ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    prune(directory, KEEP)
    return path


def _by_recency(root: Path) -> list[Path]:
    def key(path: Path) -> tuple[float, str]:
        try:
            return (path.stat().st_mtime, path.name)
        except OSError:
            return (0.0, path.name)

    return sorted(root.iterdir(), key=key, reverse=True)


def latest_entry(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    entries = _by_recency(root)
    return entries[0] if entries else None


def prune(root: Path, keep: int = KEEP, max_age: float | None = None) -> int:
    """按修改时间保留最新 `keep` 个条目；超过 `max_age` 秒的条目也删掉。返回删除数。"""
    if not root.is_dir():
        return 0
    now = time.time()
    removed = 0
    for index, entry in enumerate(_by_recency(root)):
        try:
            expired = max_age is not None and now - entry.stat().st_mtime > max_age
            if index < keep and not expired:
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def cleanup(project_id: str | None = None) -> dict[str, int]:
    """按保留期清理运行产物：报告、诊断包、探索快照、trace。

    浏览器命令开始时自动调用，保证目录不会无限增长。
    报告很小只按份数保留；截图、页面 HTML、trace 这类大文件同时按时间清理。
    """
    project_id = project_id or ""
    return {
        "reports": prune(reports_dir(project_id), KEEP),
        "artifacts": prune(artifacts_dir(project_id), ARTIFACT_KEEP, ARTIFACT_MAX_AGE),
        "probes": prune(probes_dir(project_id), PROBE_KEEP, PROBE_MAX_AGE),
        "traces": prune(traces_dir(project_id), TRACE_KEEP, TRACE_MAX_AGE),
    }


def clear(root: Path, prefix: str | None = None) -> int:
    """删除 `root` 下全部条目；`prefix` 非空时只删该前缀的条目。返回删除数。"""
    if not root.is_dir():
        return 0
    removed = 0
    for entry in _by_recency(root):
        if prefix is not None and not entry.name.startswith(prefix):
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def clear_artifacts(project_id: str | None = None, flow: str | None = None) -> int:
    """删除诊断包；给了 `flow` 只删该流程的。流程通过后清理自己的旧诊断包。"""
    prefix = f"{flow}-" if flow else None
    return clear(artifacts_dir(project_id or ""), prefix)


def clean_all(project_id: str | None = None) -> dict[str, int]:
    """立即清空诊断包、探索快照和 trace；报告只保留最近 KEEP 份。"""
    project_id = project_id or ""
    return {
        "reports": prune(reports_dir(project_id), KEEP),
        "artifacts": clear(artifacts_dir(project_id)),
        "probes": clear(probes_dir(project_id)),
        "traces": clear(traces_dir(project_id)),
    }
