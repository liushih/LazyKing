import pytest
import yaml

from runtime.jenkins.config import (
    JenkinsConfigError,
    load_jenkins_config,
    read_token,
    save_credentials,
)

FAKE = "fake-jenkins-token-123"  # noqa: secrets

FULL_YAML = """
jenkins:
  base_url: http://jenkins.example.com
  user: liushihao
  token_key: JENKINS_TOKEN
modules:
  order-service:
    paths: [order-service/]
    jobs: {dev: b2d-order-dev}
    params: {BRANCH: "{branch}"}
  pay-service:
    paths: [pay-service/]
    jobs: {dev: b2d-pay-dev}
"""


def _project(tmp_path):
    project = tmp_path / "projects" / "demo"
    project.mkdir(parents=True, exist_ok=True)
    return project


def _write(tmp_path, text):
    project = _project(tmp_path)
    (project / "jenkins.yaml").write_text(text, encoding="utf-8")
    return project


def test_load_reads_modules_in_yaml_order(tmp_path):
    _write(tmp_path, FULL_YAML)
    cfg = load_jenkins_config("demo", home=tmp_path)
    assert [m.name for m in cfg.modules] == ["order-service", "pay-service"]
    assert cfg.baseline == "origin/dev"
    assert cfg.build_timeout_minutes == 30
    assert cfg.base_url == "http://jenkins.example.com"
    assert cfg.modules[0].jobs == {"dev": "b2d-order-dev"}
    assert cfg.modules[0].params == {"BRANCH": "{branch}"}
    assert cfg.modules[1].params == {}


def test_load_missing_file_names_path(tmp_path):
    _project(tmp_path)
    with pytest.raises(JenkinsConfigError) as exc:
        load_jenkins_config("demo", home=tmp_path)
    assert "jenkins.yaml" in str(exc.value)


@pytest.mark.parametrize("missing", ["base_url", "user", "token_key"])
def test_load_rejects_missing_required_fields(tmp_path, missing):
    data = yaml.safe_load(FULL_YAML)
    del data["jenkins"][missing]
    _write(tmp_path, yaml.safe_dump(data))
    with pytest.raises(JenkinsConfigError) as exc:
        load_jenkins_config("demo", home=tmp_path)
    assert missing in str(exc.value)


def test_load_rejects_module_without_jobs_or_paths(tmp_path):
    data = yaml.safe_load(FULL_YAML)
    del data["modules"]["order-service"]["jobs"]
    _write(tmp_path, yaml.safe_dump(data))
    with pytest.raises(JenkinsConfigError):
        load_jenkins_config("demo", home=tmp_path)

    data = yaml.safe_load(FULL_YAML)
    data["modules"]["order-service"]["paths"] = [""]
    _write(tmp_path, yaml.safe_dump(data))
    with pytest.raises(JenkinsConfigError):
        load_jenkins_config("demo", home=tmp_path)


def test_load_allows_empty_modules(tmp_path):
    _write(
        tmp_path,
        "jenkins:\n  base_url: http://jenkins.example.com\n  user: u\n  token_key: JENKINS_TOKEN\n",
    )
    assert load_jenkins_config("demo", home=tmp_path).modules == []


def test_read_token_missing_reports_key_only(tmp_path):
    project = _project(tmp_path)
    (project / ".env").write_text("OTHER=value-should-not-leak\n", encoding="utf-8")
    with pytest.raises(JenkinsConfigError) as exc:
        read_token("demo", "JENKINS_TOKEN", home=tmp_path)
    assert "JENKINS_TOKEN" in str(exc.value)
    assert "value-should-not-leak" not in str(exc.value)


def test_read_token_returns_value(tmp_path):
    project = _project(tmp_path)
    (project / ".env").write_text(f"JENKINS_TOKEN={FAKE}\n", encoding="utf-8")
    assert read_token("demo", "JENKINS_TOKEN", home=tmp_path) == FAKE


def test_save_credentials_creates_yaml_and_env(tmp_path):
    save_credentials("demo", "http://jenkins.example.com", "liushihao", FAKE, home=tmp_path)
    project = tmp_path / "projects" / "demo"
    text = (project / "jenkins.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["jenkins"] == {
        "base_url": "http://jenkins.example.com",
        "user": "${JENKINS_USER}",
        "token_key": "JENKINS_TOKEN",
    }
    assert data["modules"] == {}
    assert data["baseline"] == "origin/dev"
    assert FAKE not in text
    assert (
        yaml.safe_load((project / "personal.yaml").read_text(encoding="utf-8"))[
            "JENKINS_USER"
        ]
        == "liushihao"
    )
    assert f"JENKINS_TOKEN={FAKE}" in (project / ".env").read_text(encoding="utf-8")


def test_save_credentials_preserves_existing_modules(tmp_path):
    data = yaml.safe_load(FULL_YAML)
    data["baseline"] = "origin/test"
    _write(tmp_path, yaml.safe_dump(data))
    save_credentials("demo", "http://new.example.com", "newuser", FAKE, home=tmp_path)
    saved = yaml.safe_load((tmp_path / "projects" / "demo" / "jenkins.yaml").read_text(encoding="utf-8"))
    assert saved["baseline"] == "origin/test"
    assert list(saved["modules"]) == ["order-service", "pay-service"]
    assert saved["jenkins"]["base_url"] == "http://new.example.com"
    assert saved["jenkins"]["user"] == "newuser"


def test_save_credentials_env_edge_cases(tmp_path):
    project = _project(tmp_path)
    env = project / ".env"

    env.write_text("OTHER=1", encoding="utf-8")  # 无结尾换行
    save_credentials("demo", "http://j.example.com", "u", FAKE, home=tmp_path)
    assert env.read_text(encoding="utf-8").splitlines() == ["OTHER=1", f"JENKINS_TOKEN={FAKE}"]

    env.write_text("JENKINS_TOKEN=old\nOTHER=1\n", encoding="utf-8")  # 旧值被替换
    save_credentials("demo", "http://j.example.com", "u", FAKE, home=tmp_path)
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines.count(f"JENKINS_TOKEN={FAKE}") == 1
    assert not any("old" in line for line in lines)
    assert "OTHER=1" in lines

    save_credentials("demo", "http://j.example.com", "u", FAKE + "\n", home=tmp_path)  # 换行被去掉
    assert f"JENKINS_TOKEN={FAKE}\n" in env.read_text(encoding="utf-8")
    assert f"JENKINS_TOKEN={FAKE}\n\n" not in env.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "text",
    [
        "jenkins: [unclosed",
        "- just\n- a list\n",
        "jenkins: oops\n",
        "jenkins: {base_url: http://j.example.com, user: u, token_key: K}\nmodules: oops\n",
        "jenkins: {base_url: http://j.example.com, user: u, token_key: K}\nbuild_timeout_minutes: soon\n",
        "jenkins: {base_url: http://j.example.com, user: u, token_key: K}\n"
        "modules: {m: {paths: oops, jobs: {dev: j}}}\n",
        "jenkins: {base_url: http://j.example.com, user: u, token_key: K}\n"
        "modules: {m: {paths: [a/], jobs: oops}}\n",
    ],
)
def test_malformed_yaml_raises_config_error_not_traceback(tmp_path, text):
    _write(tmp_path, text)
    with pytest.raises(JenkinsConfigError):
        load_jenkins_config("demo", home=tmp_path)


PLACEHOLDER_JENKINS = """
jenkins:
  base_url: http://jenkins.example.com
  user: ${JENKINS_USER}
  token_key: JENKINS_TOKEN
modules:
  order-service:
    paths: [order-service/]
    jobs: {dev: b2d-order-dev}
"""


def test_load_substitutes_personal_user(tmp_path):
    project = _write(tmp_path, PLACEHOLDER_JENKINS)
    (project / "personal.yaml").write_text(
        "JENKINS_USER: liushihao\n", encoding="utf-8"
    )
    cfg = load_jenkins_config("demo", home=tmp_path)
    assert cfg.user == "liushihao"


def test_save_credentials_placeholder_mode_writes_personal_and_preserves_shared(tmp_path):
    project = _write(tmp_path, PLACEHOLDER_JENKINS)
    warnings = save_credentials(
        "demo", "http://jenkins.example.com", "liushihao", FAKE, home=tmp_path
    )
    data = yaml.safe_load((project / "jenkins.yaml").read_text(encoding="utf-8"))
    assert data["jenkins"]["user"] == "${JENKINS_USER}"
    assert data["modules"]
    assert (
        yaml.safe_load((project / "personal.yaml").read_text(encoding="utf-8"))[
            "JENKINS_USER"
        ]
        == "liushihao"
    )
    assert warnings == []


def test_save_credentials_legacy_literal_mode_updates_shared(tmp_path):
    project = _write(tmp_path, FULL_YAML)
    warnings = save_credentials(
        "demo", "http://new.example.com", "newuser", FAKE, home=tmp_path
    )
    assert "${JENKINS_USER}" not in (project / "jenkins.yaml").read_text(
        encoding="utf-8"
    )
    assert warnings and "占位符" in warnings[0]
