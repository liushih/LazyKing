"""本地数据目录与 .env 解析。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    pass


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FULL_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def substitute(value: Any, env: dict[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _FULL_VAR.fullmatch(value)
        if whole:
            key = whole.group(1)
            if key not in env:
                raise ConfigError(f"未定义变量 {key}")
            return env[key]

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in env:
                raise ConfigError(f"未定义变量 {key}")
            raw = env[key]
            if not isinstance(raw, str):
                raise ConfigError(f"变量 {key} 不是字符串，不能嵌入字符串")
            return raw

        return _VAR.sub(repl, value)
    if isinstance(value, dict):
        return {k: substitute(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, env) for v in value]
    return value


def _find_up(name: str, start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        candidate = parent / name
        if candidate.is_dir():
            return candidate
    return None


def data_home() -> Path:
    env = os.getenv("DATA_TOOLS_HOME")
    if env:
        return Path(env)
    local = _find_up(".data-tools")
    if local is not None:
        return local
    return Path.home() / ".data-tools"


def project_dir(project_id: str) -> Path:
    return data_home() / "projects" / project_id


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def load_values(project_dir: Path) -> dict[str, Any]:
    """读取个人值：personal.yaml 提供非敏感值，.env 覆盖同名键。"""
    base = Path(project_dir)
    values: dict[str, Any] = {}
    personal = base / "personal.yaml"
    if personal.exists():
        try:
            data = yaml.safe_load(personal.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"personal.yaml 不是合法 YAML：{personal}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"personal.yaml 顶层必须是映射：{personal}")
        values.update(data)
    values.update(load_env(base / ".env"))
    return values


def write_env_key(path: Path, key: str, value: str) -> None:
    """按 KEY= 覆盖或追加，保留其他行；POSIX 下把文件权限设为 0600。"""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    entry = f"{key}={value}"
    replaced = False
    out: list[str] = []
    for line in lines:
        if "=" in line and line.split("=", 1)[0].strip() == key:
            if not replaced:
                out.append(entry)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def resolve_project(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    cfg = data_home() / "config.yaml"
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        default = data.get("default_project")
        if default:
            return str(default)
    raise ConfigError("未指定项目：传入 project_id，或在 config.yaml 设置 default_project")
