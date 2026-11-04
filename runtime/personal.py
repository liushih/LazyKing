"""个人配置的扫描、检查与写入。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import config


class PersonalConfigError(config.ConfigError):
    pass


@dataclass(frozen=True)
class KeySpec:
    description: str = ""
    type: str = "string"
    default_from: str = "none"


@dataclass(frozen=True)
class MissingKey:
    key: str
    target: str
    description: str = ""
    default_from: str = "none"


@dataclass(frozen=True)
class Drift:
    file: str
    kind: str
    key: str | None = None
    message: str = ""


@dataclass(frozen=True)
class CapabilityReport:
    status: str
    missing: tuple[MissingKey, ...] = ()
    drift: tuple[Drift, ...] = ()


@dataclass(frozen=True)
class CheckReport:
    project: str
    capabilities: dict[str, CapabilityReport]
    drift: tuple[Drift, ...] = ()


CAPABILITIES = ("git", "jenkins", "report", "adapter", "browser")
SHARED_FILES = {
    "git": ("git_hosts.yaml",),
    "jenkins": ("jenkins.yaml",),
    "report": ("report.yaml",),
    "adapter": ("adapter.yaml",),
    "browser": ("browser/browser.yaml",),
}
TOKEN_KEY_PATHS = {
    "git": (("host", "token_key"),),
    "jenkins": (("jenkins", "token_key"),),
}
KNOWN_PERSONAL = {
    "git_hosts.yaml": (("user_tag",), ("repo_path",)),
    "jenkins.yaml": (("jenkins", "user"),),
    "report.yaml": (
        ("git", "repos"),
        ("git", "authors"),
        ("zentao", "account"),
        ("zentao", "authors"),
    ),
}
BROWSER_SCAN_PATHS = (
    ("envs",),
    ("defaults", "profile"),
    ("login", "url"),
    ("login", "username"),
    ("login", "password"),
)
BROWSER_RUNTIME_VARS = {"BASE_URL", "username", "password"}
PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")
KEY_DEFAULTS = {
    "USER_TAG": KeySpec("Git 分支与提交使用的个人标识", "string", "git_user_name"),
    "REPO_PATH": KeySpec("本机业务仓库根目录", "string", "repo_root"),
    "REPORT_REPOS": KeySpec("报告要统计的仓库路径，可多个", "list", "repo_root"),
    "JENKINS_USER": KeySpec("Jenkins 登录账号", "string", "user_tag"),
    "GIT_AUTHORS": KeySpec("Git 提交里可能出现的作者名或账号", "list", "git_user_name"),
    "ZENTAO_ACCOUNT": KeySpec("禅道登录账号", "string", "none"),
    "ZENTAO_AUTHORS": KeySpec("禅道任务或 Bug 里可能出现的完成人", "list", "git_user_name"),
}
SECRET_HINTS = ("PASSWORD", "TOKEN", "SECRET", "PRIVATE")


def _base(project_id: str, home: Path | None) -> Path:
    if home is not None:
        return Path(home) / "projects" / project_id
    return config.project_dir(project_id)


def _read_yaml(path: Path, label: str) -> dict | None:
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PersonalConfigError(f"{label} 不是合法 YAML：{path}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PersonalConfigError(f"{label} 顶层必须是映射：{path}")
    return data


def _placeholders(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(PLACEHOLDER.findall(value))
    if isinstance(value, dict):
        return {name for item in value.values() for name in _placeholders(item)}
    if isinstance(value, list):
        return {name for item in value for name in _placeholders(item)}
    return set()


def _get(data: Any, path: tuple[str, ...]) -> Any:
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _read_specs(path: Path) -> dict[str, KeySpec]:
    data = _read_yaml(path, "personal.example.yaml")
    if data is None:
        return {}
    raw = data.get("keys") or {}
    if not isinstance(raw, dict):
        raise PersonalConfigError(f"personal.example.yaml 的 keys 必须是映射：{path}")
    specs: dict[str, KeySpec] = {}
    for key, item in raw.items():
        if isinstance(item, dict):
            specs[str(key)] = KeySpec(
                description=str(item.get("description") or ""),
                type=str(item.get("type") or "string"),
                default_from=str(item.get("default_from") or "none"),
            )
        else:
            specs[str(key)] = KeySpec()
    return specs


def _read_secret_keys(path: Path) -> set[str]:
    return set(config.load_env(path))


def _has_literal(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER.search(value)
    if isinstance(value, list):
        return any(_has_literal(item) for item in value)
    return False


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _scan(capability: str, base: Path) -> tuple[str, set[str], list[Drift], set[str]]:
    placeholders: set[str] = set()
    drift: list[Drift] = []
    token_keys: set[str] = set()
    found = False

    for rel in SHARED_FILES[capability]:
        data = _read_yaml(base / rel, rel)
        if data is None:
            continue
        found = True

        if capability == "browser":
            for parts in BROWSER_SCAN_PATHS:
                placeholders |= _placeholders(_get(data, parts))
        else:
            placeholders |= _placeholders(data)

        for parts in KNOWN_PERSONAL.get(rel, ()):
            value = _get(data, parts)
            if _has_literal(value):
                name = ".".join(parts)
                drift.append(
                    Drift(
                        rel,
                        "literal_personal_value",
                        name,
                        f"{rel} 的 {name} 仍是个人值，建议改成占位符",
                    )
                )

        for text in _iter_strings(data):
            if ABSOLUTE_PATH.match(text):
                drift.append(
                    Drift(rel, "absolute_path", None, f"{rel} 出现绝对路径：{text}")
                )

        for parts in TOKEN_KEY_PATHS.get(capability, ()):
            value = _get(data, parts)
            if isinstance(value, str) and value.strip() and not PLACEHOLDER.search(value):
                token_keys.add(value.strip())

    if not found:
        return "absent", set(), [], set()

    if capability == "browser":
        placeholders -= BROWSER_RUNTIME_VARS

    deduped: list[Drift] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in drift:
        key = (item.file, item.kind, item.key)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return "ok", placeholders, deduped, token_keys


def check(
    project_id: str, capability: str | None = None, home: Path | None = None
) -> CheckReport:
    if capability is not None and capability not in CAPABILITIES:
        raise PersonalConfigError(f"未知能力：{capability}")

    base = _base(project_id, home)
    caps = (capability,) if capability else CAPABILITIES
    global_drift: list[Drift] = []
    invalid_message: str | None = None

    try:
        personal_values = config.load_values(base)
    except config.ConfigError as exc:
        personal_values = {}
        invalid_message = str(exc)

    try:
        specs = _read_specs(base / "personal.example.yaml")
    except PersonalConfigError as exc:
        specs = {}
        if invalid_message is None:
            invalid_message = str(exc)

    if not (base / "personal.example.yaml").exists():
        global_drift.append(
            Drift(
                "personal.example.yaml",
                "missing_example",
                None,
                "缺少 personal.example.yaml，运行 config example --write",
            )
        )

    secret_keys = _read_secret_keys(base / ".env.example")
    env_values = config.load_env(base / ".env")
    capabilities: dict[str, CapabilityReport] = {}
    all_placeholders: set[str] = set()

    for cap in caps:
        if invalid_message is not None:
            capabilities[cap] = CapabilityReport(
                "invalid",
                (),
                (Drift("personal.yaml", "invalid_personal_yaml", None, invalid_message),),
            )
            continue

        try:
            status, placeholders, drift, token_keys = _scan(cap, base)
        except PersonalConfigError as exc:
            capabilities[cap] = CapabilityReport(
                "invalid",
                (),
                (Drift(SHARED_FILES[cap][0], "invalid_yaml", None, str(exc)),),
            )
            continue

        if status == "absent":
            capabilities[cap] = CapabilityReport("absent")
            continue

        all_placeholders |= placeholders
        missing: list[MissingKey] = []
        seen: set[tuple[str, str, str | None]] = set()

        def add(item: Drift) -> None:
            key = (item.file, item.kind, item.key)
            if key not in seen:
                seen.add(key)
                drift.append(item)

        for key in sorted(placeholders):
            in_specs = key in specs
            in_secrets = key in secret_keys
            if in_specs and in_secrets:
                add(
                    Drift(
                        "-",
                        "duplicate_declaration",
                        key,
                        f"{key} 同时出现在 personal.example.yaml 与 .env.example",
                    )
                )
                continue
            if not in_specs and not in_secrets:
                add(
                    Drift(
                        "-",
                        "undeclared_variable",
                        key,
                        f"共享配置引用了未声明的变量 {key}",
                    )
                )
                continue
            if in_specs:
                if key not in personal_values:
                    spec = specs[key]
                    missing.append(
                        MissingKey(key, "personal", spec.description, spec.default_from)
                    )
            elif key not in env_values:
                missing.append(MissingKey(key, "secret"))

        for key in sorted(token_keys):
            if key not in secret_keys:
                add(
                    Drift(
                        "-",
                        "undeclared_variable",
                        key,
                        f"token_key {key} 未在 .env.example 声明",
                    )
                )
            elif key not in env_values:
                missing.append(MissingKey(key, "secret"))

        missing.sort(key=lambda item: (item.target, item.key))
        capabilities[cap] = CapabilityReport(
            "missing" if missing else "ok", tuple(missing), tuple(drift)
        )

    if capability is None:
        for key in sorted(set(specs) - all_placeholders):
            global_drift.append(
                Drift(
                    "personal.example.yaml",
                    "unused_declaration",
                    key,
                    f"{key} 已声明但共享配置未使用",
                )
            )

    return CheckReport(project_id, capabilities, tuple(global_drift))


def report_json(report: CheckReport) -> dict[str, Any]:
    def drift_json(item: Drift) -> dict[str, Any]:
        return {
            "file": item.file,
            "kind": item.kind,
            "key": item.key,
            "message": item.message,
        }

    return {
        "project": report.project,
        "capabilities": {
            name: {
                "status": cap.status,
                "missing": [
                    {
                        "key": item.key,
                        "target": item.target,
                        "description": item.description,
                        "default_from": item.default_from,
                    }
                    for item in cap.missing
                ],
                "drift": [drift_json(item) for item in cap.drift],
            }
            for name, cap in report.capabilities.items()
        },
        "drift": [drift_json(item) for item in report.drift],
    }


def _personal_path(base: Path) -> Path:
    return base / "personal.yaml"


def _read_personal(base: Path) -> dict[str, Any]:
    path = _personal_path(base)
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PersonalConfigError(f"personal.yaml 不是合法 YAML：{path}") from exc
    if not isinstance(data, dict):
        raise PersonalConfigError(f"personal.yaml 顶层必须是映射：{path}")
    return data


def _atomic_write_text(path: Path, text: str, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    if private and os.name == "posix":
        path.chmod(0o600)


def _write_personal(base: Path, data: dict[str, Any]) -> None:
    text = yaml.safe_dump(data, sort_keys=True, allow_unicode=True)
    _atomic_write_text(_personal_path(base), text, private=True)


def _coerce(raw: str, kind: str) -> Any:
    if kind == "list":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def set_value(
    project_id: str,
    values: dict[str, str],
    *,
    allow_unknown: bool = False,
    home: Path | None = None,
) -> list[str]:
    base = _base(project_id, home)
    example = base / "personal.example.yaml"
    if not example.exists():
        raise PersonalConfigError(
            "缺少 personal.example.yaml，先运行 config example --write"
        )
    specs = _read_specs(example)
    secret_keys = _read_secret_keys(base / ".env.example")

    converted: dict[str, Any] = {}
    for key, raw in values.items():
        if key in secret_keys:
            raise PersonalConfigError(f"{key} 是密钥，请用 set-secret 写入 .env")
        if key not in specs and not allow_unknown:
            raise PersonalConfigError(f"{key} 未在 personal.example.yaml 声明")
        spec = specs.get(key, KeySpec())
        converted[key] = _coerce(raw, spec.type)

    data = _read_personal(base)
    data.update(converted)
    _write_personal(base, data)
    return list(converted)


def set_secret(
    project_id: str, key: str, value: str, *, home: Path | None = None
) -> None:
    base = _base(project_id, home)
    secret_keys = _read_secret_keys(base / ".env.example")
    if key not in secret_keys:
        raise PersonalConfigError(f"{key} 未在 .env.example 声明")
    value = value.strip()
    if not value:
        raise PersonalConfigError("密钥值不能为空")
    base.mkdir(parents=True, exist_ok=True)
    config.write_env_key(base / ".env", key, value)


def write_known_value(
    project_id: str, key: str, value: Any, *, home: Path | None = None
) -> None:
    base = _base(project_id, home)
    data = _read_personal(base)
    data[key] = value
    _write_personal(base, data)


def build_example(project_id: str, home: Path | None = None) -> dict[str, KeySpec]:
    base = _base(project_id, home)
    secret_keys = _read_secret_keys(base / ".env.example")
    placeholders: set[str] = set()
    for capability in CAPABILITIES:
        try:
            status, found, _, _ = _scan(capability, base)
        except PersonalConfigError:
            continue
        if status == "ok":
            placeholders |= found
    return {
        key: KEY_DEFAULTS.get(key, KeySpec())
        for key in sorted(placeholders)
        if key not in secret_keys
    }


def write_example(
    project_id: str, *, force: bool = False, home: Path | None = None
) -> Path | None:
    base = _base(project_id, home)
    path = base / "personal.example.yaml"
    if path.exists() and not force:
        return None
    specs = build_example(project_id, home=home)
    data = {
        "version": 1,
        "keys": {
            key: {
                "description": spec.description,
                "type": spec.type,
                "default_from": spec.default_from,
            }
            for key, spec in specs.items()
        },
    }
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    _atomic_write_text(path, text)
    return path


def secret_candidates(project_id: str, home: Path | None = None) -> set[str]:
    base = _base(project_id, home)
    declared = _read_secret_keys(base / ".env.example")
    candidates: set[str] = set()
    for capability in CAPABILITIES:
        try:
            status, placeholders, _, token_keys = _scan(capability, base)
        except PersonalConfigError:
            continue
        if status != "ok":
            continue
        candidates |= {key for key in token_keys if key not in declared}
        for key in placeholders:
            if key in declared:
                continue
            if any(hint in key.upper() for hint in SECRET_HINTS):
                candidates.add(key)
    return candidates
