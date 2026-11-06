"""项目级浏览器控件记忆：失败一次就记一条，下次按控件检索。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .flow import FlowResult

_ENTRY = re.compile(r"^## (?P<id>M\d+)(?:\s+(?P<control>.+))?$")
_FIELD = re.compile(r"^- (?P<name>现象|页面|流程|出现次数)：(?P<value>.*)$")


class MemoryError(Exception):
    pass


@dataclass(frozen=True)
class MemoryNote:
    id: str
    control: str
    symptom: str
    page: str
    flow: str
    seen: int


def memory_path(project_dir: Path) -> Path:
    return Path(project_dir) / "browser" / "controls.md"


def load_memory(project_dir: Path) -> list[MemoryNote]:
    path = memory_path(project_dir)
    if not path.exists():
        return []
    notes: list[MemoryNote] = []
    current: dict[str, str] | None = None

    def finish() -> None:
        if current is None:
            return
        try:
            seen = int(current.get("出现次数", "1"))
        except ValueError as exc:
            raise MemoryError(f"{path} 的出现次数不是整数：{current.get('出现次数')}") from exc
        notes.append(MemoryNote(
            id=current["id"],
            control=current.get("control", ""),
            symptom=current.get("现象", ""),
            page=current.get("页面", ""),
            flow=current.get("流程", ""),
            seen=seen,
        ))

    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ENTRY.match(line.strip())
        if match:
            finish()
            current = {"id": match.group("id"), "control": (match.group("control") or "").strip()}
            continue
        field = _FIELD.match(line.strip())
        if field and current is not None:
            current[field.group("name")] = field.group("value").strip()
    finish()
    return notes


def matching_notes(project_dir: Path, text: str) -> list[MemoryNote]:
    folded = text.casefold()
    return [note for note in load_memory(project_dir) if note.control and note.control.casefold() in folded]


def record_failure(
    project_dir: Path,
    result: FlowResult,
    *,
    control: str,
    page: str = "",
) -> MemoryNote:
    failure = result.failure
    if failure is None:
        raise MemoryError("通过的流程不记录控件问题")
    symptom = " ".join(part for part in (failure.message, failure.expected, failure.actual) if part).strip()
    notes = load_memory(project_dir)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for index, note in enumerate(notes):
        if note.control == control and note.symptom == symptom and note.flow == result.flow:
            updated = MemoryNote(note.id, note.control, note.symptom, page or note.page, note.flow, note.seen + 1)
            notes[index] = updated
            _write(project_dir, notes, now)
            return updated

    created = MemoryNote(f"M{len(notes) + 1}", control.strip(), symptom, page, result.flow, 1)
    notes.append(created)
    _write(project_dir, notes, now)
    return created


def _write(project_dir: Path, notes: list[MemoryNote], updated_at: str) -> None:
    path = memory_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 浏览器控件记录",
        "",
        "执行浏览器流程前先按控件名检索。同一控件、同一现象重复出现时只累加出现次数。",
        "",
        f"最近更新：{updated_at}",
        "",
    ]
    for note in notes:
        lines.extend([
            f"## {note.id} {note.control}".rstrip(),
            "",
            f"- 现象：{note.symptom}",
            f"- 页面：{note.page}",
            f"- 流程：{note.flow}",
            f"- 出现次数：{note.seen}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")
