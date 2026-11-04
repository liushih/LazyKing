import pytest

from scripts import mongo, query, redis, run


@pytest.fixture
def missing_personal(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "adapter.yaml").write_text(
        "version: 1\nproject: demo\nenvs:\n  dev:\n    base_url: ${BASE}\n",
        encoding="utf-8",
    )
    return proj


@pytest.mark.parametrize(
    "runner,args",
    [
        (run.main, ["--project", "demo", "--entity", "x"]),
        (query.main, ["--project", "demo", "--sql", "select 1"]),
        (mongo.main, ["--project", "demo", "--collection", "c", "--find", "{}"]),
        (redis.main, ["--project", "demo", "--cmd", "GET x"]),
    ],
)
def test_cli_reports_missing_personal_config(runner, args, missing_personal, capsys):
    assert runner(args) == 2
    out = capsys.readouterr().out
    assert "[配置]" in out and "project-setup" in out
