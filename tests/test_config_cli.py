import io
import json
import sys

import pytest

from scripts import config as config_cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    base = tmp_path / "projects" / "demo"
    base.mkdir(parents=True)
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    (base / "personal.example.yaml").write_text(
        "version: 1\nkeys:\n  USER_TAG:\n    description: 标识\n", encoding="utf-8"
    )
    (base / ".env.example").write_text("JENKINS_TOKEN=\n", encoding="utf-8")
    (base / "jenkins.yaml").write_text(
        "jenkins:\n  base_url: http://j\n  user: u\n  token_key: JENKINS_TOKEN\n",
        encoding="utf-8",
    )
    return tmp_path


def test_check_json_exit_2_when_capability_missing(home, capsys):
    code = config_cli.main(
        ["--project", "demo", "check", "--capability", "git", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["capabilities"]["git"]["status"] == "missing"


def test_check_without_capability_does_not_fail_on_missing(home, capsys):
    assert config_cli.main(["--project", "demo", "check"]) == 0
    assert "USER_TAG" in capsys.readouterr().out


def test_set_writes_value(home, capsys):
    assert config_cli.main(["--project", "demo", "set", "USER_TAG=lsh"]) == 0
    assert "已写入 personal.yaml" in capsys.readouterr().out


def test_set_secret_never_prints_value(home, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("secret-value\n"))
    assert config_cli.main(["--project", "demo", "set-secret", "JENKINS_TOKEN"]) == 0
    out = capsys.readouterr().out
    assert "secret-value" not in out
    assert "JENKINS_TOKEN" in out


def test_example_write_creates_file(home, capsys):
    path = home / "projects" / "demo" / "personal.example.yaml"
    path.unlink()
    assert config_cli.main(["--project", "demo", "example", "--write"]) == 0
    assert path.exists()


def test_invalid_yaml_exit_3(home, capsys):
    (home / "projects" / "demo" / "jenkins.yaml").write_text(
        "jenkins: [unclosed\n", encoding="utf-8"
    )
    assert config_cli.main(["--project", "demo", "check", "--capability", "jenkins"]) == 3
