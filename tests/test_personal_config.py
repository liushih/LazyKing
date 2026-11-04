import json

import pytest
import yaml

from runtime import personal


def _project(tmp_path, *, personal_example=None, env_example=None, personal=None, env=None):
    base = tmp_path / "projects" / "demo"
    base.mkdir(parents=True)
    if personal_example is not None:
        (base / "personal.example.yaml").write_text(personal_example, encoding="utf-8")
    if env_example is not None:
        (base / ".env.example").write_text(env_example, encoding="utf-8")
    if personal is not None:
        (base / "personal.yaml").write_text(personal, encoding="utf-8")
    if env is not None:
        (base / ".env").write_text(env, encoding="utf-8")
    return base


def test_check_reports_missing_personal_key(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG:\n    description: 标识\n",
        env_example="",
    )
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "missing"
    assert [m.key for m in report.capabilities["git"].missing] == ["USER_TAG"]
    assert report.capabilities["git"].missing[0].target == "personal"


def test_check_reports_missing_secret_token_key(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="JENKINS_TOKEN=\n",
        env="",
    )
    (base / "jenkins.yaml").write_text(
        "jenkins:\n  base_url: http://j\n  user: u\n  token_key: JENKINS_TOKEN\n",
        encoding="utf-8",
    )
    report = personal.check("demo", "jenkins", home=tmp_path)
    assert [m.key for m in report.capabilities["jenkins"].missing] == ["JENKINS_TOKEN"]
    assert report.capabilities["jenkins"].missing[0].target == "secret"


def test_check_reports_undeclared_placeholder(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "adapter.yaml").write_text(
        "envs:\n  dev:\n    base_url: ${NEW_VAR}\n", encoding="utf-8"
    )
    report = personal.check("demo", "adapter", home=tmp_path)
    assert any(
        d.kind == "undeclared_variable" and d.key == "NEW_VAR"
        for d in report.capabilities["adapter"].drift
    )


def test_check_reports_duplicate_declaration(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="USER_TAG=\n",
    )
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    report = personal.check("demo", "git", home=tmp_path)
    assert any(
        d.kind == "duplicate_declaration" for d in report.capabilities["git"].drift
    )


def test_check_warns_literal_personal_value(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "git_hosts.yaml").write_text(
        "user_tag: lsh\nrepo_path: C:/x\n", encoding="utf-8"
    )
    report = personal.check("demo", "git", home=tmp_path)
    assert any(
        d.kind == "literal_personal_value" and d.key == "user_tag"
        for d in report.capabilities["git"].drift
    )


def test_check_warns_absolute_path(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "report.yaml").write_text(
        "git:\n  repos: []\n  authors: []\n"
        "zentao:\n  base_url: http://z\n  template: C:/project/demo\n",
        encoding="utf-8",
    )
    report = personal.check("demo", "report", home=tmp_path)
    assert any(
        d.kind == "absolute_path" for d in report.capabilities["report"].drift
    )


def test_check_skips_browser_builtins_and_flow_vars(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  WEB_USERNAME: {}\n",
        env_example="WEB_PASSWORD=\n",
        personal="WEB_USERNAME: u\n",
        env="WEB_PASSWORD=p\n",
    )
    browser = base / "browser"
    (browser / "flows").mkdir(parents=True)
    (browser / "browser.yaml").write_text(
        "envs:\n  dev:\n    base_url: http://localhost\n"
        "login:\n  url: http://localhost/login\n"
        "  username: ${WEB_USERNAME}\n  password: ${WEB_PASSWORD}\n"
        "  steps:\n    - fill: {placeholder: 手机号}\n      value: ${username}\n"
        "    - fill: {placeholder: 密码}\n      value: ${password}\n",
        encoding="utf-8",
    )
    (browser / "flows" / "smoke.yaml").write_text(
        "steps:\n  - goto: ${BASE_URL}/x?order=${order_no}\n", encoding="utf-8"
    )
    report = personal.check("demo", "browser", home=tmp_path)
    keys = {m.key for m in report.capabilities["browser"].missing}
    assert "username" not in keys and "password" not in keys and "order_no" not in keys


def test_check_ignores_dotted_runtime_placeholders(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "adapter.yaml").write_text(
        "entities:\n  order:\n    steps:\n      - id: create\n        body:\n"
        "          no: ${ctx.external_no}\n",
        encoding="utf-8",
    )
    report = personal.check("demo", "adapter", home=tmp_path)
    assert all(m.key != "ctx" for m in report.capabilities["adapter"].missing)


def test_check_absent_capability(tmp_path):
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "absent"


def test_check_invalid_yaml_reports_invalid(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "jenkins.yaml").write_text("jenkins: [unclosed\n", encoding="utf-8")
    report = personal.check("demo", "jenkins", home=tmp_path)
    assert report.capabilities["jenkins"].status == "invalid"


def test_check_invalid_personal_yaml_reports_invalid(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="",
    )
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    (base / "personal.yaml").write_text("USER_TAG: [\n", encoding="utf-8")
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "invalid"


def test_report_json_has_no_values(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="",
        personal="USER_TAG: PERSONAL_VALUE_LEAK\n",
    )
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    payload = json.dumps(
        personal.report_json(personal.check("demo", "git", home=tmp_path)),
        ensure_ascii=False,
    )
    assert "PERSONAL_VALUE_LEAK" not in payload


def test_set_value_writes_personal_yaml(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n  REPO_PATH: {}\n",
        env_example="",
    )
    personal.set_value(
        "demo", {"USER_TAG": "lsh", "REPO_PATH": "C:/repo"}, home=tmp_path
    )
    data = yaml.safe_load(
        (tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8")
    )
    assert data == {"REPO_PATH": "C:/repo", "USER_TAG": "lsh"}


def test_set_value_splits_list(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  GIT_AUTHORS: {type: list}\n",
        env_example="",
    )
    personal.set_value("demo", {"GIT_AUTHORS": "liushihao, 刘师豪"}, home=tmp_path)
    data = yaml.safe_load(
        (tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8")
    )
    assert data["GIT_AUTHORS"] == ["liushihao", "刘师豪"]


def test_set_value_rejects_secret_key(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="JENKINS_TOKEN=\n",
    )
    with pytest.raises(personal.PersonalConfigError, match="set-secret"):
        personal.set_value("demo", {"JENKINS_TOKEN": "x"}, home=tmp_path)


def test_set_value_rejects_unknown_key(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    with pytest.raises(personal.PersonalConfigError, match="未在 personal.example.yaml"):
        personal.set_value("demo", {"TYPO": "x"}, home=tmp_path)


def test_set_secret_writes_env_only(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="JENKINS_TOKEN=\n",
    )
    personal.set_secret("demo", "JENKINS_TOKEN", "secret-value", home=tmp_path)
    base = tmp_path / "projects" / "demo"
    assert "JENKINS_TOKEN=secret-value" in (base / ".env").read_text(encoding="utf-8")
    assert not (base / "personal.yaml").exists()


def test_set_secret_rejects_personal_key(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="",
    )
    with pytest.raises(personal.PersonalConfigError, match=".env.example"):
        personal.set_secret("demo", "USER_TAG", "x", home=tmp_path)


def test_set_secret_rejects_empty(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="JENKINS_TOKEN=\n",
    )
    with pytest.raises(personal.PersonalConfigError, match="不能为空"):
        personal.set_secret("demo", "JENKINS_TOKEN", "  ", home=tmp_path)


def test_write_example_does_not_overwrite(tmp_path):
    path = tmp_path / "projects" / "demo" / "personal.example.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("version: 1\nkeys: {USER_TAG: {description: old}}\n", encoding="utf-8")
    assert personal.write_example("demo", home=tmp_path) is None
    assert "description: old" in path.read_text(encoding="utf-8")


def test_write_example_generates_known_defaults(tmp_path):
    base = _project(tmp_path)
    (base / "git_hosts.yaml").write_text(
        "user_tag: ${USER_TAG}\nrepo_path: ${REPO_PATH}\n", encoding="utf-8"
    )
    personal.write_example("demo", home=tmp_path)
    data = yaml.safe_load(
        (base / "personal.example.yaml").read_text(encoding="utf-8")
    )
    assert data["keys"]["USER_TAG"]["default_from"] == "git_user_name"
    assert data["keys"]["REPO_PATH"]["default_from"] == "repo_root"


def test_write_known_value_works_without_example(tmp_path):
    personal.write_known_value("demo", "USER_TAG", "lsh", home=tmp_path)
    data = yaml.safe_load(
        (tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8")
    )
    assert data["USER_TAG"] == "lsh"


def test_check_does_not_treat_url_path_as_absolute_path(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="",
    )
    (base / "browser").mkdir()
    (base / "browser" / "browser.yaml").write_text(
        "login:\n  success:\n    url_path: /index\n", encoding="utf-8"
    )
    report = personal.check("demo", "browser", home=tmp_path)
    assert not any(
        d.kind == "absolute_path" for d in report.capabilities["browser"].drift
    )


def test_check_treats_empty_personal_value_as_missing(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="",
        personal='USER_TAG: ""\n',
    )
    (base / "git_hosts.yaml").write_text("user_tag: ${USER_TAG}\n", encoding="utf-8")
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "missing"
    assert [m.key for m in report.capabilities["git"].missing] == ["USER_TAG"]


def test_check_treats_empty_secret_as_missing(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys: {}\n",
        env_example="JENKINS_TOKEN=\n",
        env="JENKINS_TOKEN=\n",
    )
    (base / "jenkins.yaml").write_text(
        "jenkins:\n  base_url: http://j\n  user: u\n  token_key: JENKINS_TOKEN\n",
        encoding="utf-8",
    )
    report = personal.check("demo", "jenkins", home=tmp_path)
    assert [m.key for m in report.capabilities["jenkins"].missing] == ["JENKINS_TOKEN"]


def test_check_allows_empty_list_value(tmp_path):
    base = _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  ZENTAO_AUTHORS: {type: list}\n",
        env_example="",
        personal="ZENTAO_AUTHORS: []\n",
    )
    (base / "report.yaml").write_text(
        "zentao:\n  authors: ${ZENTAO_AUTHORS}\n", encoding="utf-8"
    )
    report = personal.check("demo", "report", home=tmp_path)
    assert report.capabilities["report"].status == "ok"


def test_set_value_rejects_empty_scalar(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  USER_TAG: {}\n",
        env_example="",
    )
    with pytest.raises(personal.PersonalConfigError, match="不能为空"):
        personal.set_value("demo", {"USER_TAG": "  "}, home=tmp_path)


def test_set_value_allows_empty_list(tmp_path):
    _project(
        tmp_path,
        personal_example="version: 1\nkeys:\n  GIT_AUTHORS: {type: list}\n",
        env_example="",
    )
    personal.set_value("demo", {"GIT_AUTHORS": ""}, home=tmp_path)
    data = yaml.safe_load(
        (tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8")
    )
    assert data["GIT_AUTHORS"] == []
