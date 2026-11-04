"""项目级的 Jenkins 配置与令牌读写。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from runtime import config, personal

DEFAULT_TOKEN_KEY = "JENKINS_TOKEN"
DEFAULT_BASELINE = "origin/dev"
DEFAULT_TIMEOUT_MINUTES = 30


class JenkinsConfigError(Exception):
    pass


@dataclass
class ModuleSpec:
    name: str
    paths: list[str]
    jobs: dict[str, str]
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class JenkinsConfig:
    base_url: str
    user: str
    token_key: str
    baseline: str = DEFAULT_BASELINE
    build_timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES
    modules: list[ModuleSpec] = field(default_factory=list)


def _base(project_id: str, home: Path | None) -> Path:
    return (Path(home) / "projects" / project_id) if home is not None else config.project_dir(project_id)


def _parse_module(name: str, raw: object) -> ModuleSpec:
    if not isinstance(raw, dict):
        raise JenkinsConfigError(f"模块 {name} 的配置必须是映射")
    raw_paths, raw_jobs, raw_params = raw.get("paths") or [], raw.get("jobs") or {}, raw.get("params") or {}
    if not isinstance(raw_paths, list):
        raise JenkinsConfigError(f"模块 {name} 的 paths 必须是列表")
    if not isinstance(raw_jobs, dict) or not isinstance(raw_params, dict):
        raise JenkinsConfigError(f"模块 {name} 的 jobs / params 必须是映射")
    paths = [str(p) for p in raw_paths]
    if not paths or any(not p.strip() for p in paths):
        raise JenkinsConfigError(f"模块 {name} 的 paths 不能为空，且不能含空路径")
    jobs = {str(k): str(v) for k, v in raw_jobs.items()}
    if not jobs:
        raise JenkinsConfigError(f"模块 {name} 至少要有一个 jobs（环境 → 任务名）")
    params = {str(k): str(v) for k, v in raw_params.items()}
    return ModuleSpec(name=name, paths=paths, jobs=jobs, params=params)


def load_jenkins_config(project_id: str, home: Path | None = None) -> JenkinsConfig:
    path = _base(project_id, home) / "jenkins.yaml"
    if not path.exists():
        raise JenkinsConfigError(f"未找到 jenkins.yaml：{path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise JenkinsConfigError(f"jenkins.yaml 不是合法的 YAML：{path}") from exc
    if not isinstance(data, dict):
        raise JenkinsConfigError("jenkins.yaml 顶层必须是映射")
    try:
        data = config.substitute(data, config.load_values(_base(project_id, home)))
    except config.ConfigError as exc:
        raise JenkinsConfigError(
            f"jenkins.yaml 变量解析失败：{exc}；缺少个人配置时先运行 project-setup"
        ) from exc
    section = data.get("jenkins") or {}
    if not isinstance(section, dict):
        raise JenkinsConfigError("jenkins.yaml 的 jenkins 必须是映射")
    values = {}
    for key in ("base_url", "user", "token_key"):
        value = str(section.get(key) or "").strip()
        if not value:
            raise JenkinsConfigError(f"jenkins.yaml 缺少 jenkins.{key}")
        values[key] = value

    raw_modules = data.get("modules") or {}
    if not isinstance(raw_modules, dict):
        raise JenkinsConfigError("jenkins.yaml 的 modules 必须是映射（模块名 → 配置）")
    modules = [_parse_module(str(name), raw) for name, raw in raw_modules.items()]
    try:
        timeout = int(data.get("build_timeout_minutes") or DEFAULT_TIMEOUT_MINUTES)
    except (TypeError, ValueError):
        raise JenkinsConfigError("build_timeout_minutes 必须是整数（分钟）") from None
    return JenkinsConfig(
        base_url=values["base_url"],
        user=values["user"],
        token_key=values["token_key"],
        baseline=str(data.get("baseline") or DEFAULT_BASELINE),
        build_timeout_minutes=timeout,
        modules=modules,
    )


def read_token(project_id: str, token_key: str, home: Path | None = None) -> str:
    env = config.load_env(_base(project_id, home) / ".env")
    value = env.get(token_key, "")
    if not value:
        raise JenkinsConfigError(f"缺少令牌 {token_key}，请先运行 setup 或在项目 .env 中填写")
    return value


def save_credentials(
    project_id: str,
    base_url: str,
    user: str,
    token: str,
    token_key: str = DEFAULT_TOKEN_KEY,
    home: Path | None = None,
) -> list[str]:
    project = _base(project_id, home)
    project.mkdir(parents=True, exist_ok=True)

    yaml_path = project / "jenkins.yaml"
    data = (
        (yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {})
        if yaml_path.exists()
        else {}
    )
    if not isinstance(data, dict):
        raise JenkinsConfigError("jenkins.yaml 顶层必须是映射")
    section = data.get("jenkins")
    if not isinstance(section, dict):
        section = {}
        data["jenkins"] = section

    warnings: list[str] = []
    current_user = str(section.get("user") or "").strip()
    if current_user in ("", "${JENKINS_USER}"):
        personal.write_known_value(
            project_id, "JENKINS_USER", user.strip(), home=home
        )
        section["user"] = "${JENKINS_USER}"
        section.setdefault("base_url", base_url.strip())
        section.setdefault("token_key", token_key)
    else:
        section["base_url"] = base_url.strip()
        section["user"] = user.strip()
        section["token_key"] = token_key
        warnings.append(
            "共享 jenkins.yaml 的 user 仍是字面值，建议改成占位符 ${JENKINS_USER}"
        )

    data.setdefault("baseline", DEFAULT_BASELINE)
    data.setdefault("modules", {})
    yaml_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    config.write_env_key(project / ".env", token_key, token.strip())
    return warnings
