"""版本比较、更新检查缓存与检查命令。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"
DEFAULT_INTERVAL_HOURS = 24
GIT_TIMEOUT_SECONDS = 5

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

CACHE_NAME = ".update-check.json"


class UpdateError(Exception):
    """远端检查失败时抛出。"""


@dataclass(frozen=True)
class CheckResult:
    available: bool
    local: str
    remote: str | None
    message: str


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
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_bool(value, default: bool) -> bool:
    """把 YAML 里的常见真/假写法统一成 bool；无法识别时用 default。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "yes", "on", "1"):
            return True
        if normalized in ("false", "no", "off", "0"):
            return False
    return default


def _coerce_interval_hours(value, default: int) -> int:
    """接受整数或数字字符串；负数与非数字回落到 default。"""
    if isinstance(value, bool):
        return default
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return default
    return hours if hours >= 0 else default


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
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict):
            section = data.get("data_tools")
            if isinstance(section, dict):
                for key in settings:
                    if section.get(key) is not None:
                        settings[key] = section[key]
    settings["update_check"] = _coerce_bool(settings["update_check"], True)
    settings["check_interval_hours"] = _coerce_interval_hours(
        settings["check_interval_hours"], DEFAULT_INTERVAL_HOURS
    )
    if not isinstance(settings["source"], str) or not settings["source"].strip():
        settings["source"] = DEFAULT_SOURCE
    return settings


def read_cache(project_dir: Path) -> dict:
    """读 .data-tools/.update-check.json；缺失、非 JSON 或非字典时返回空字典。"""
    path = Path(project_dir) / ".data-tools" / CACHE_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
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


def _run_ls_remote(args: list[str]) -> str:
    """执行 git ls-remote；返回非零时抛 UpdateError。"""
    try:
        result = subprocess.run(
            ["git", "ls-remote", *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    if result.returncode != 0:
        raise UpdateError(result.stderr.strip() or "git ls-remote 失败")
    return result.stdout


def remote_versions(source: str) -> list[Version]:
    """远端所有 vX.Y.Z tag，按 git 输出顺序返回。"""
    output = _run_ls_remote(["--tags", "--refs", source, "v*"])
    versions: list[Version] = []
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        version = parse_version(parts[-1].rsplit("/", 1)[-1])
        if version is not None:
            versions.append(version)
    return versions


def remote_head(source: str) -> str | None:
    """远端 main 分支的短 SHA；不存在时返回 None。"""
    output = _run_ls_remote([source, "refs/heads/main"])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "refs/heads/main":
            return parts[0][:7]
    return None


def _version_text(version: Version) -> str:
    return f"{version.major}.{version.minor}.{version.patch}"


def _version_update_message(local: str, remote: str) -> str:
    return f"[data-tools] 本地 v{local}，远端 v{remote}。运行 data-tools/update.ps1 更新。"


def _commit_update_message(local: str, commit: str) -> str:
    return f"[data-tools] 本地 v{local}，远端 main@{commit}。运行 data-tools/update.ps1 更新。"


def _same_commit(local: str | None, remote: str | None) -> bool:
    """短/长 SHA 互为前缀即同一提交；unknown 或缺失无法判断时按相同处理。"""
    if not local or not remote:
        return True
    local = local.strip().lower()
    remote = remote.strip().lower()
    if not local or not remote or local == "unknown" or remote == "unknown":
        return True
    return local.startswith(remote) or remote.startswith(local)


def _write_cache_safely(
    project_dir: Path, latest_version: str | None, latest_commit: str | None, now: datetime
) -> None:
    """缓存写失败（如只读目录）不应让检查抛异常。"""
    try:
        write_cache(project_dir, latest_version, latest_commit, now)
    except OSError:
        pass


def check_update(
    project_dir: Path, source: str | None = None, now: datetime | None = None
) -> CheckResult:
    """检查是否有新版本；本地 VERSION 缺失或无效时返回不可用，不抛异常。"""
    project_dir = Path(project_dir)
    settings = load_settings(project_dir)
    version_path = project_dir / "data-tools" / "VERSION"
    meta = read_local_version(project_dir)

    raw_version = meta.get("version")
    raw_text = raw_version.strip() if isinstance(raw_version, str) else ""
    local_version = parse_version(raw_text) if raw_text else None
    local = _version_text(local_version) if local_version is not None else raw_text

    local_commit = meta.get("source_commit")
    if not isinstance(local_commit, str) or not local_commit:
        local_commit = None

    if not settings["update_check"]:
        return CheckResult(False, local, None, "已禁用更新检查。")
    if not version_path.is_file():
        return CheckResult(False, local, None, "未找到 data-tools/VERSION，无法检查更新。")
    if local_version is None:
        return CheckResult(
            False, local, None, "data-tools/VERSION 中的 version 缺失或无效，无法检查更新。"
        )

    source = source or settings["source"]
    now = now or datetime.now(timezone.utc)
    interval = settings["check_interval_hours"]

    cache = read_cache(project_dir)
    if cache_is_fresh(cache, now, interval):
        cached_version = cache.get("latest_version")
        cached_version = cached_version if isinstance(cached_version, str) else None
        cached_commit = cache.get("latest_commit")
        cached_commit = cached_commit if isinstance(cached_commit, str) else None
        if cached_version is not None and is_newer(local, cached_version):
            return CheckResult(
                True, local, cached_version, _version_update_message(local, cached_version)
            )
        if cached_commit is not None and not _same_commit(local_commit, cached_commit):
            return CheckResult(True, local, None, _commit_update_message(local, cached_commit))
        return CheckResult(False, local, cached_version, f"已是最新版本 v{local}。")

    try:
        versions = remote_versions(source)
        latest = max(versions) if versions else None
        if latest is not None:
            latest_text = _version_text(latest)
            _write_cache_safely(project_dir, latest_text, None, now)
            if is_newer(local, latest_text):
                return CheckResult(
                    True, local, latest_text, _version_update_message(local, latest_text)
                )
            return CheckResult(False, local, latest_text, f"已是最新版本 v{local}。")

        head = remote_head(source)
        _write_cache_safely(project_dir, None, head, now)
        if head is not None and not _same_commit(local_commit, head):
            return CheckResult(True, local, None, _commit_update_message(local, head))
        return CheckResult(False, local, None, f"已是最新版本 v{local}。")
    except (UpdateError, subprocess.TimeoutExpired, OSError):
        # 不写缓存：失败不应在检查间隔内压掉后续重试。
        # 固定文案，避免把带 user:token 的远端地址带进 stdout/日志。
        return CheckResult(False, local, None, "检查更新失败，请稍后重试。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查并更新 data-tools")
    parser.add_argument("--project-dir", type=Path, default=Path("."), help="业务仓库根目录")
    parser.add_argument("--source", help="远端仓库地址，默认读取配置")
    parser.add_argument("--check", action="store_true", help="只检查是否有新版本")
    parser.add_argument("--quiet", action="store_true", help="无新版本时不输出提示")
    args = parser.parse_args(argv)

    if not args.check:
        # 更新落盘由后续任务的 apply_update 补充。
        return 0

    result = check_update(args.project_dir, args.source)
    if result.message and (not args.quiet or result.available):
        print(result.message)
    return 10 if result.available else 0


if __name__ == "__main__":
    raise SystemExit(main())
