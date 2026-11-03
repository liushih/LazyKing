"""浏览器运行报告。"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from runtime.config import data_home

from .flow import FlowResult

KEEP = 20


def timestamp() -> str:
    now = datetime.now()
    return f"{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}"


def reports_dir(project_id: str) -> Path:
    return data_home() / "browser" / "reports"


def artifacts_dir(project_id: str) -> Path:
    return data_home() / "browser" / "artifacts"


def write_report(project_id: str, result: FlowResult) -> Path:
    directory = reports_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{result.flow}-{timestamp()}"
    path = directory / f"{stem}.json"
    index = 2
    while path.exists():
        path = directory / f"{stem}-{index}.json"
        index += 1
    path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    prune(directory, KEEP)
    return path


def prune(root: Path, keep: int = KEEP) -> None:
    if not root.is_dir():
        return
    entries = sorted(root.iterdir(), key=lambda path: path.name, reverse=True)
    for entry in entries[keep:]:
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError:
            pass
