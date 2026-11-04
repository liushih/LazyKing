import pytest

from runtime import config


def test_data_home_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.data_home() == tmp_path


def test_load_env_keeps_equals_and_hash(tmp_path):
    p = tmp_path / ".env"
    p.write_text("PW=a=b#c\n", encoding="utf-8")
    assert config.load_env(p)["PW"] == "a=b#c"


def test_resolve_project_explicit_beats_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project("explicit") == "explicit"


def test_resolve_project_falls_back_to_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project(None) == "from_config"


def test_resolve_project_without_any_source_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(config.ConfigError):
        config.resolve_project(None)


def test_substitute_keeps_nested_structure():
    assert config.substitute({"a": ["${N}"]}, {"N": "5"}) == {"a": ["5"]}


def test_substitute_reports_missing_var():
    with pytest.raises(config.ConfigError, match="NOPE"):
        config.substitute("${NOPE}", {})


def test_data_home_finds_project_local(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_TOOLS_HOME", raising=False)
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    monkeypatch.chdir(project)
    assert config.data_home() == (project / ".data-tools").resolve()


def test_data_home_finds_nearest_ancestor(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_TOOLS_HOME", raising=False)
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert config.data_home() == (project / ".data-tools").resolve()


def test_data_home_env_beats_project_local(monkeypatch, tmp_path):
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    override = tmp_path / "override"
    override.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("DATA_TOOLS_HOME", str(override))
    assert config.data_home() == override


def test_load_values_merges_personal_and_env(tmp_path):
    (tmp_path / "personal.yaml").write_text(
        "USER_TAG: lsh\nGIT_AUTHORS: [liushihao, 刘师豪]\nFROM_ENV: personal\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("FROM_ENV=dotenv\nTOKEN=secret\n", encoding="utf-8")
    assert config.load_values(tmp_path) == {
        "USER_TAG": "lsh",
        "GIT_AUTHORS": ["liushihao", "刘师豪"],
        "FROM_ENV": "dotenv",
        "TOKEN": "secret",
    }


def test_load_values_without_personal_reads_env_only(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    assert config.load_values(tmp_path) == {"TOKEN": "x"}


def test_load_values_rejects_non_mapping(tmp_path):
    (tmp_path / "personal.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="personal.yaml"):
        config.load_values(tmp_path)


def test_load_values_rejects_bad_yaml(tmp_path):
    (tmp_path / "personal.yaml").write_text("a: [\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="personal.yaml"):
        config.load_values(tmp_path)


def test_substitute_whole_value_returns_list():
    assert config.substitute("${AUTHORS}", {"AUTHORS": ["a", "b"]}) == ["a", "b"]


def test_substitute_rejects_list_inside_string():
    with pytest.raises(config.ConfigError, match="AUTHORS"):
        config.substitute("x-${AUTHORS}", {"AUTHORS": ["a"]})


def test_write_env_key_replaces_and_preserves_others(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER=1\nJENKINS_TOKEN=old\n", encoding="utf-8")
    config.write_env_key(path, "JENKINS_TOKEN", "new")
    assert path.read_text(encoding="utf-8").splitlines() == ["OTHER=1", "JENKINS_TOKEN=new"]
