import pytest
import yaml

from runtime.git_host.config import (
    GitHostConfigError,
    load_git_host_config,
    read_token,
    save_user_tag,
)

YAML = """user_tag: lsh
repo_path: C:/project/demo
host:
  kind: gitlab
  base_url: http://git.example.com
  project_path: grp/demo
  token_key: GITLAB_TOKEN_DEMO
branches:
  dev: dev
  test: test
  prod: prod
rules:
  forbid_commit_paths: [pom.xml, vite.config.ts]
"""

FAKE_TOKEN = "fake-token-value-for-tests"


@pytest.fixture
def home(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(YAML, encoding="utf-8")
    (proj / ".env").write_text(f"GITLAB_TOKEN_DEMO={FAKE_TOKEN}\n", encoding="utf-8")
    return tmp_path


def test_loads_host_and_rules(home):
    cfg = load_git_host_config("demo", home=home)
    assert cfg.kind == "gitlab" and cfg.project_path == "grp/demo"
    assert cfg.user_tag == "lsh"
    assert cfg.forbid_commit_paths == ["pom.xml", "vite.config.ts"]


def test_reads_token_from_project_env(home):
    assert read_token("demo", "GITLAB_TOKEN_DEMO", home=home) == FAKE_TOKEN


def test_missing_token_names_key_only(home):
    with pytest.raises(GitHostConfigError) as exc:
        read_token("demo", "GITHUB_TOKEN_NOPE", home=home)
    assert "GITHUB_TOKEN_NOPE" in str(exc.value)
    assert FAKE_TOKEN not in str(exc.value)


def test_unknown_host_kind_rejected(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("kind: gitlab", "kind: bitbucket"), encoding="utf-8")
    with pytest.raises(GitHostConfigError, match="bitbucket"):
        load_git_host_config("demo", home=home)


def test_save_user_tag_is_persisted(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("user_tag: lsh", "user_tag: "), encoding="utf-8")
    save_user_tag("demo", "zhang", home=home)
    assert load_git_host_config("demo", home=home).user_tag == "zhang"


def test_missing_user_tag_is_empty_not_default(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(YAML.replace("user_tag: lsh", "user_tag: "), encoding="utf-8")
    assert load_git_host_config("demo", home=home).user_tag == ""


PLACEHOLDER_YAML = (
    "user_tag: ${USER_TAG}\nrepo_path: ${REPO_PATH}\n"
    "host: {kind: gitlab, base_url: http://g, project_path: a/b, token_key: T}\n"
)


def _placeholder_project(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(PLACEHOLDER_YAML, encoding="utf-8")
    return proj


def test_load_substitutes_personal_values(tmp_path):
    proj = _placeholder_project(tmp_path)
    (proj / "personal.yaml").write_text(
        "USER_TAG: lsh\nREPO_PATH: C:/x\n", encoding="utf-8"
    )
    cfg = load_git_host_config("demo", home=tmp_path)
    assert cfg.user_tag == "lsh"
    assert cfg.repo_path.as_posix() == "C:/x"


def test_load_missing_personal_guides_setup(tmp_path):
    _placeholder_project(tmp_path)
    with pytest.raises(GitHostConfigError, match="project-setup"):
        load_git_host_config("demo", home=tmp_path)


def test_save_user_tag_writes_personal_in_placeholder_mode(tmp_path):
    proj = _placeholder_project(tmp_path)
    (proj / "personal.example.yaml").write_text(
        "version: 1\nkeys: {USER_TAG: {description: 标识}}\n", encoding="utf-8"
    )
    save_user_tag("demo", "zhang", home=tmp_path)
    assert (
        yaml.safe_load((proj / "personal.yaml").read_text(encoding="utf-8"))[
            "USER_TAG"
        ]
        == "zhang"
    )
    assert "${USER_TAG}" in (proj / "git_hosts.yaml").read_text(encoding="utf-8")
