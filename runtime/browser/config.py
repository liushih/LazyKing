"""浏览器测试配置与流程 YAML 解析。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from runtime.config import ConfigError, data_home, load_env, project_dir, substitute

from .apiwatch import ApiWatchConfig


class BrowserConfigError(Exception):
    pass


class FlowNotFoundError(BrowserConfigError):
    pass


@dataclass(frozen=True)
class EnvConfig:
    name: str
    base_url: str
    values: dict[str, str]


@dataclass(frozen=True)
class LoginConfig:
    url: str
    username: str | None
    password: str | None
    steps: list[dict[str, Any]]
    impl: str | None
    success_url_path: str | None
    success_localstorage: dict[str, str]


@dataclass(frozen=True)
class VarDef:
    required: bool = False
    default: str | None = None
    description: str = ""


@dataclass(frozen=True)
class FlowDef:
    name: str
    description: str
    env: str | None
    vars: dict[str, VarDef]
    steps: list[dict[str, Any]]
    path: Path


@dataclass(frozen=True)
class BrowserConfig:
    project: str
    envs: dict[str, EnvConfig]
    default_env: str
    timeout_ms: int
    headless: bool
    profile: Path | None
    login: LoginConfig | None
    api_watch: ApiWatchConfig = field(default_factory=ApiWatchConfig)

_BROWSER_FIELDS = {"version", "project", "envs", "defaults", "login"}
_DEFAULT_FIELDS = {"env", "timeout_ms", "headless", "profile", "api_watch"}
_API_WATCH_FIELDS = {"enabled", "ignore", "success_codes", "grace_ms"}
_LOGIN_FIELDS = {"url", "username", "password", "steps", "impl", "success"}
_SUCCESS_FIELDS = {"url_path", "localStorage"}
_FLOW_FIELDS = {"version", "flow", "description", "env", "vars", "steps"}
_VAR_FIELDS = {"required", "default", "description"}
_STEP_FIELDS = {"name", "timeout", "optional", "value", "as", "allow_api_error"}
_ACTIONS = {"goto", "click", "fill", "press", "select", "check", "hover", "use_row", "impl"}
_VALUE_ACTIONS = {"fill", "select"}


def _check_mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise BrowserConfigError(f"{where} 必须是映射")
    return value


def _check_keys(data: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise BrowserConfigError(f"{where} 含未知字段：{', '.join(unknown)}")


def _substitute(value: Any, env: dict[str, str], where: str) -> Any:
    try:
        return substitute(value, env)
    except ConfigError as exc:
        raise BrowserConfigError(f"{where} 变量解析失败：{exc}") from exc


def _path(project_id: str, *parts: str) -> Path:
    return project_dir(project_id).joinpath(*parts)


def _load_yaml(path: Path, where: str) -> dict:
    if not path.exists():
        raise BrowserConfigError(f"{where} 不存在：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BrowserConfigError(f"{where} YAML 非法：{exc}") from exc
    return _check_mapping(data, where)


def _validate_step(step: Any, where: str, *, require_name: bool) -> dict:
    step = _check_mapping(step, where)
    allowed = set(_STEP_FIELDS) | set(_ACTIONS)
    allowed |= {key for key in step if key.startswith(("wait_", "expect_"))}
    _check_keys(step, allowed, where)

    name = step.get("name")
    if require_name and (not isinstance(name, str) or not name.strip()):
        raise BrowserConfigError(f"{where} 缺少 name")
    actions = [key for key in step if key in _ACTIONS]
    if len(actions) > 1:
        raise BrowserConfigError(f"{where} 最多只能包含一个动作：{'/'.join(_ACTIONS)}")
    if not actions:
        if "wait_response" in step:
            raise BrowserConfigError(f"{where} 的 wait_response 需要动作")
        if not any(key.startswith(("wait_", "expect_")) for key in step):
            raise BrowserConfigError(f"{where} 至少需要一个动作或 wait_/expect_ 断言")
    else:
        action = actions[0]
        if action in _VALUE_ACTIONS and "value" not in step:
            raise BrowserConfigError(f"{where} 的 {action} 缺少 value")

    timeout = step.get("timeout")
    if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
        raise BrowserConfigError(f"{where} 的 timeout 必须是正整数")
    if "optional" in step and not isinstance(step["optional"], bool):
        raise BrowserConfigError(f"{where} 的 optional 必须是布尔值")
    if "as" in step and (not isinstance(step["as"], str) or not step["as"].strip()):
        raise BrowserConfigError(f"{where} 的 as 必须是非空字符串")
    allow = step.get("allow_api_error")
    if allow is not None and not (
        isinstance(allow, bool) or (isinstance(allow, list) and all(isinstance(item, str) for item in allow))
    ):
        raise BrowserConfigError(f"{where} 的 allow_api_error 必须是布尔值或 URL 片段列表")
    return step


def _load_api_watch(raw: Any) -> ApiWatchConfig:
    raw = _check_mapping(raw or {}, "browser.yaml defaults.api_watch")
    _check_keys(raw, _API_WATCH_FIELDS, "browser.yaml defaults.api_watch")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise BrowserConfigError("browser.yaml defaults.api_watch.enabled 必须是布尔值")
    ignore = raw.get("ignore") or []
    if not isinstance(ignore, list) or not all(isinstance(item, str) for item in ignore):
        raise BrowserConfigError("browser.yaml defaults.api_watch.ignore 必须是 URL 片段列表")
    grace_ms = raw.get("grace_ms", ApiWatchConfig.grace_ms)
    if isinstance(grace_ms, bool) or not isinstance(grace_ms, int) or grace_ms < 0:
        raise BrowserConfigError("browser.yaml defaults.api_watch.grace_ms 必须是非负整数")
    success_codes = raw.get("success_codes")
    if success_codes is None:
        codes = ApiWatchConfig.success_codes
    elif isinstance(success_codes, list) and success_codes:
        codes = tuple(str(code).strip().lower() for code in success_codes)
    else:
        raise BrowserConfigError("browser.yaml defaults.api_watch.success_codes 必须是非空列表")
    return ApiWatchConfig(enabled=enabled, ignore=tuple(ignore), success_codes=codes, grace_ms=grace_ms)


def _load_login(raw: Any, lookup: dict[str, str]) -> LoginConfig | None:
    if raw is None:
        return None
    raw = _check_mapping(raw, "browser.yaml login")
    _check_keys(raw, _LOGIN_FIELDS, "browser.yaml login")

    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        raise BrowserConfigError("browser.yaml login.url 必填")
    login_lookup = {**lookup, "BASE_URL": "${BASE_URL}"}
    url = _substitute(url, login_lookup, "browser.yaml login.url")

    steps = raw.get("steps") or []
    impl = raw.get("impl")
    if steps and impl:
        raise BrowserConfigError("browser.yaml login.steps 与 login.impl 只能二选一")
    if not steps and not impl:
        raise BrowserConfigError("browser.yaml login 需要 steps 或 impl")
    if not isinstance(steps, list):
        raise BrowserConfigError("browser.yaml login.steps 必须是列表")
    for index, step in enumerate(steps, 1):
        _validate_step(step, f"browser.yaml login.steps[{index}]", require_name=False)
    if impl is not None and (not isinstance(impl, str) or ":" not in impl):
        raise BrowserConfigError("browser.yaml login.impl 必须写成 文件:函数")

    username = raw.get("username")
    password = raw.get("password")
    if username is not None:
        username = str(_substitute(username, lookup, "browser.yaml login.username"))
    if password is not None:
        password = str(_substitute(password, lookup, "browser.yaml login.password"))

    success = _check_mapping(raw.get("success"), "browser.yaml login.success")
    _check_keys(success, _SUCCESS_FIELDS, "browser.yaml login.success")
    url_path = success.get("url_path")
    if url_path is not None and (not isinstance(url_path, str) or not url_path.startswith("/")):
        raise BrowserConfigError("browser.yaml login.success.url_path 必须以 / 开头")
    local_storage = success.get("localStorage") or {}
    if not isinstance(local_storage, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in local_storage.items()
    ):
        raise BrowserConfigError("browser.yaml login.success.localStorage 必须是字符串映射")
    if not url_path and not local_storage:
        raise BrowserConfigError("browser.yaml login.success 至少提供 url_path 或 localStorage")

    return LoginConfig(
        url=url,
        username=username,
        password=password,
        steps=steps,
        impl=impl,
        success_url_path=url_path,
        success_localstorage=local_storage,
    )


def load_browser_config(project_id: str) -> BrowserConfig:
    path = _path(project_id, "browser", "browser.yaml")
    data = _load_yaml(path, "browser.yaml")
    _check_keys(data, _BROWSER_FIELDS, "browser.yaml")

    if data.get("version") != 1:
        raise BrowserConfigError("browser.yaml 的 version 必须为 1")
    project = data.get("project")
    if project != project_id:
        raise BrowserConfigError(
            f"browser.yaml 的 project 与项目目录不一致：{project!r} != {project_id!r}"
        )

    envs_raw = _check_mapping(data.get("envs"), "browser.yaml envs")
    if not envs_raw:
        raise BrowserConfigError("browser.yaml envs 不能为空")

    dotenv = load_env(project_dir(project_id) / ".env")
    lookup = {**os.environ, **dotenv}
    envs: dict[str, EnvConfig] = {}
    for name, raw in envs_raw.items():
        raw = _check_mapping(raw, f"browser.yaml envs.{name}")
        values = _substitute(raw, lookup, f"browser.yaml envs.{name}")
        base_url = values.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise BrowserConfigError(f"browser.yaml envs.{name}.base_url 必填")
        envs[str(name)] = EnvConfig(
            name=str(name),
            base_url=base_url,
            values={str(key): str(value) for key, value in values.items()},
        )

    defaults = _check_mapping(data.get("defaults") or {}, "browser.yaml defaults")
    _check_keys(defaults, _DEFAULT_FIELDS, "browser.yaml defaults")
    default_env = str(defaults.get("env", "dev"))
    if default_env not in envs:
        raise BrowserConfigError(f"browser.yaml defaults.env 不存在：{default_env}")
    timeout_ms = defaults.get("timeout_ms", 15000)
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise BrowserConfigError("browser.yaml defaults.timeout_ms 必须是正整数")
    headless = defaults.get("headless", False)
    if not isinstance(headless, bool):
        raise BrowserConfigError("browser.yaml defaults.headless 必须是布尔值")
    profile = defaults.get("profile")
    if profile is not None:
        profile = Path(str(_substitute(profile, lookup, "browser.yaml defaults.profile")))

    login = _load_login(data.get("login"), lookup)
    return BrowserConfig(
        project=project_id,
        envs=envs,
        default_env=default_env,
        timeout_ms=timeout_ms,
        headless=headless,
        profile=profile,
        login=login,
        api_watch=_load_api_watch(defaults.get("api_watch")),
    )


def load_flow(project_id: str, flow_name: str) -> FlowDef:
    path = _path(project_id, "browser", "flows", f"{flow_name}.yaml")
    if not path.exists():
        raise FlowNotFoundError(f"流程不存在：{flow_name}")
    data = _load_yaml(path, f"流程 {flow_name}")
    _check_keys(data, _FLOW_FIELDS, f"流程 {flow_name}")

    if data.get("version") != 1:
        raise BrowserConfigError(f"流程 {flow_name} 的 version 必须为 1")
    name = data.get("flow")
    if name != flow_name:
        raise BrowserConfigError(f"流程 {flow_name} 的 flow 与文件名不一致：{name!r}")
    description = str(data.get("description", ""))
    env = data.get("env")
    if env is not None:
        env = str(env)

    vars_raw = _check_mapping(data.get("vars") or {}, f"流程 {flow_name} vars")
    var_defs: dict[str, VarDef] = {}
    for var_name, raw in vars_raw.items():
        raw = _check_mapping(raw, f"流程 {flow_name} vars.{var_name}")
        _check_keys(raw, _VAR_FIELDS, f"流程 {flow_name} vars.{var_name}")
        required = raw.get("required", False)
        if not isinstance(required, bool):
            raise BrowserConfigError(f"流程 {flow_name} vars.{var_name}.required 必须是布尔值")
        default = raw.get("default")
        if default is not None:
            default = str(default)
        var_defs[str(var_name)] = VarDef(
            required=required,
            default=default,
            description=str(raw.get("description", "")),
        )

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise BrowserConfigError(f"流程 {flow_name} 的 steps 必须是非空列表")
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, step in enumerate(steps_raw, 1):
        step = _validate_step(step, f"流程 {flow_name} steps[{index}]", require_name=True)
        name_key = step["name"]
        if name_key in seen:
            raise BrowserConfigError(f"流程 {flow_name} 步骤名重复：{name_key}")
        seen.add(name_key)
        steps.append(step)

    return FlowDef(
        name=flow_name,
        description=description,
        env=env,
        vars=var_defs,
        steps=steps,
        path=path,
    )


def list_flows(project_id: str) -> list[FlowDef]:
    directory = _path(project_id, "browser", "flows")
    if not directory.is_dir():
        return []
    return [load_flow(project_id, path.stem) for path in sorted(directory.glob("*.yaml"))]


def resolve_variables(
    cfg: BrowserConfig,
    flow: FlowDef,
    env_name: str,
    cli_vars: dict[str, str],
    os_env: dict[str, str] | None = None,
) -> dict[str, str]:
    if env_name not in cfg.envs:
        raise BrowserConfigError(f"未知环境：{env_name}")
    env = cfg.envs[env_name]
    source_env = os.environ if os_env is None else os_env
    values: dict[str, str] = {str(key): str(value) for key, value in source_env.items()}
    values.update(env.values)
    values["BASE_URL"] = env.base_url

    for name, var_def in flow.vars.items():
        if var_def.default is not None:
            values[name] = var_def.default
        elif not var_def.required:
            values[name] = ""
    values.update({str(key): str(value) for key, value in cli_vars.items()})

    missing = [name for name, var_def in flow.vars.items() if var_def.required and name not in values]
    if missing:
        raise BrowserConfigError(f"缺少必填变量：{', '.join(missing)}")

    resolved: dict[str, str] = {}
    for key, value in values.items():
        resolved[key] = str(_substitute(value, values, f"变量 {key}"))
    return resolved


def profile_path(cfg: BrowserConfig, env_name: str, override: Path | None = None) -> Path:
    if override is not None:
        return Path(override)
    if cfg.profile is not None:
        return cfg.profile
    return data_home() / "browser" / "profiles" / cfg.project / env_name


_PLACEHOLDER = re.compile(r"[$][{]([A-Za-z_][A-Za-z0-9_]*)[}]")


def _placeholders(value: Any) -> list[str]:
    if isinstance(value, str):
        return _PLACEHOLDER.findall(value)
    if isinstance(value, dict):
        return [name for item in value.values() for name in _placeholders(item)]
    if isinstance(value, list):
        return [name for item in value for name in _placeholders(item)]
    return []


def find_unresolved(flow: FlowDef, variables: dict[str, str]) -> list[str]:
    """流程里引用了、却没有任何来源的 ${变量}。含 impl 步骤时放行：impl 的返回值会在运行时并入变量。"""
    if any("impl" in step for step in flow.steps):
        return []
    names: list[str] = []
    for step in flow.steps:
        for name in _placeholders(step):
            if name not in variables and name not in names:
                names.append(name)
    return sorted(names)
