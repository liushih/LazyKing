"""版本比较与更新检查缓存：纯函数与读写辅助，联网检查由后续任务补充。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml

DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"
DEFAULT_INTERVAL_HOURS = 24

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

CACHE_NAME = ".update-check.json"


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int


def parse_version(text: str) -> Version | None:
    """接受 vX.Y.Z 或 X.Y.Z；其余一律返回 None。"""
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return Version(major, minor, patch)


def is_newer(local: str, remote: str) -> bool:
    """远端版本严格高于本地才为 True；任一侧无法解析时返回 False。"""
    local_version = parse_version(local)
    remote_version = parse_version(remote)
    if local_version is None or remote_version is None:
        return False
    return remote_version > local_version


def read_local_version(project_dir: Path) -> dict:
    """读 data-tools/VERSION YAML；缺失或无法解析时返回空字典。"""
    path = Path(project_dir) / "data-tools" / "VERSION"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def load_settings(project_dir: Path) -> dict:
    """读 .data-tools/config.yaml 的 data_tools 段，缺失字段用默认值补齐。"""
    settings = {
        "source": DEFAULT_SOURCE,
        "update_check": True,
        "check_interval_hours": DEFAULT_INTERVAL_HOURS,
    }
    path = Path(project_dir) / ".data-tools" / "config.yaml"
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict):
            section = data.get("data_tools")
            if isinstance(section, dict):
                for key in settings:
                    if section.get(key) is not None:
                        settings[key] = section[key]
    return settings


def read_cache(project_dir: Path) -> dict:
    """读 .data-tools/.update-check.json；缺失、非 JSON 或非字典时返回空字典。"""
    path = Path(project_dir) / ".data-tools" / CACHE_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_cache(
    project_dir: Path,
    latest_version: str | None,
    latest_commit: str | None,
    now: datetime,
) -> None:
    """把检查结果写入缓存文件，last_checked 取 now 的 ISO 文本。"""
    path = Path(project_dir) / ".data-tools" / CACHE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_checked": now.isoformat(),
        "latest_version": latest_version,
        "latest_commit": latest_commit,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_is_fresh(cache: dict, now: datetime, hours: int) -> bool:
    """last_checked 距 now 不超过 hours 即新鲜；无法解析返回 False。"""
    raw = cache.get("last_checked")
    if not isinstance(raw, str):
        return False
    try:
        checked = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=now.tzinfo)
    try:
        return (now - checked) <= timedelta(hours=hours)
    except TypeError:
        return False