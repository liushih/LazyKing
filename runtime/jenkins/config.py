"""项目级的 Jenkins 配置与令牌读写。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from runtime import config

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
    paths = [str(p) for p in (raw.get("paths") or [])]
    if not paths or any(not p.strip() for p in paths):
        raise JenkinsConfigError(f"模块 {name} 的 paths 不能为空，且不能含空路径")
    jobs = {str(k): str(v) for k, v in (raw.get("jobs") or {}).items()}
    if not jobs:
        raise JenkinsConfigError(f"模块 {name} 至少要有一个 jobs（环境 → 任务名）")
    params = {str(k): str(v) for k, v in (raw.get("params") or {}).items()}
    return ModuleSpec(name=name, paths=paths, jobs=jobs, params=params)


def load_jenkins_config(project_id: str, home: Path | None = None) -> JenkinsConfig:
    path = _base(project_id, home) / "jenkins.yaml"
    if not path.exists():
        raise JenkinsConfigError(f"未找到 jenkins.yaml：{path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("jenkins") or {}
    values = {}
    for key in ("base_url", "user", "token_key"):
        value = str(section.get(key) or "").strip()
        if not value:
            raise JenkinsConfigError(f"jenkins.yaml 缺少 jenkins.{key}")
        values[key] = value

    modules = [_parse_module(str(name), raw) for name, raw in (data.get("modules") or {}).items()]
    return JenkinsConfig(
        base_url=values["base_url"],
        user=values["user"],
        token_key=values["token_key"],
        baseline=str(data.get("baseline") or DEFAULT_BASELINE),
        build_timeout_minutes=int(data.get("build_timeout_minutes") or DEFAULT_TIMEOUT_MINUTES),
        modules=modules,
    )


def read_token(project_id: str, token_key: str, home: Path | None = None) -> str:
    env = config.load_env(_base(project_id, home) / ".env")
    value = env.get(token_key, "")
    if not value:
        raise JenkinsConfigError(f"缺少令牌 {token_key}，请先运行 setup 或在项目 .env 中填写")
    return value


def _write_env_key(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    entry = f"{key}={value}"
    replaced = False
    out: list[str] = []
    for line in lines:
        if line.split("=", 1)[0].strip() == key and "=" in line:
            if not replaced:
                out.append(entry)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(entry)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def save_credentials(
    project_id: str,
    base_url: str,
    user: str,
    token: str,
    token_key: str = DEFAULT_TOKEN_KEY,
    home: Path | None = None,
) -> None:
    project = _base(project_id, home)
    project.mkdir(parents=True, exist_ok=True)

    yaml_path = project / "jenkins.yaml"
    data = (yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}) if yaml_path.exists() else {}
    data["jenkins"] = {"base_url": base_url.strip(), "user": user.strip(), "token_key": token_key}
    data.setdefault("baseline", DEFAULT_BASELINE)
    data.setdefault("modules", {})
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    _write_env_key(project / ".env", token_key, token.strip())
