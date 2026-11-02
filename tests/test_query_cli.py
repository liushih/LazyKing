import pytest

from scripts.query import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("\n".join([
        "BASE=http://example",
        "DEV_HOST=h", "DEV_PORT=5432", "DEV_USER=u", "DEV_PASSWORD=p",
    ]) + "\n", encoding="utf-8")
    (proj / "adapter.yaml").write_text(
        """version: 1
project: demo
envs:
  dev:
    base_url: ${BASE}
    db_prefix: DEV
    database: hexin_wms
auth:
  type: none
entities:
  order:
    description: 测试单
    steps:
      - id: hook
        impl: hook.py:go
""",
        encoding="utf-8",
    )
    return proj


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.params = None
        self.closed = False
        self.committed = False

    def close(self):
        self.closed = True

    def commit(self):
        self.committed = True


def test_runs_sql_and_prints_rows(project, capsys, monkeypatch):
    conn = _Conn([("DONE",)])
    seen = {}

    def fake_execute(c, sql, params=None):
        seen["sql"] = sql
        seen["params"] = params
        return [("DONE",)], 1

    monkeypatch.setattr("scripts.query.db.execute", fake_execute)
    rc = main(
        ["--project", "demo", "--sql", "select status from t where no = %(no)s", "--param", "no=X"],
        connect_fn=lambda env, prefix, db: conn,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "DONE" in out
    assert seen["params"] == {"no": "X"}
    assert conn.closed is True


def test_commit_flag_commits_after_write(project, capsys, monkeypatch):
    conn = _Conn([])
    monkeypatch.setattr(
        "scripts.query.db.execute", lambda c, sql, params=None: ([], 0)
    )
    rc = main(
        ["--project", "demo", "--sql", "create table t (id int)", "--commit"],
        connect_fn=lambda env, prefix, db: conn,
    )
    assert rc == 0
    assert conn.committed is True
    assert conn.closed is True


def test_without_commit_flag_leaves_transaction_uncommitted(project, capsys, monkeypatch):
    conn = _Conn([])
    monkeypatch.setattr(
        "scripts.query.db.execute", lambda c, sql, params=None: ([], 0)
    )
    rc = main(
        ["--project", "demo", "--sql", "create table t (id int)"],
        connect_fn=lambda env, prefix, db: conn,
    )
    assert rc == 0
    assert conn.committed is False
    assert conn.closed is True


def test_commit_flag_does_not_commit_failed_statement(project, capsys, monkeypatch):
    conn = _Conn([])

    def boom(c, sql, params=None):
        raise RuntimeError("syntax error")

    monkeypatch.setattr("scripts.query.db.execute", boom)
    with pytest.raises(RuntimeError):
        main(
            ["--project", "demo", "--sql", "create tble t (id int)", "--commit"],
            connect_fn=lambda env, prefix, db: conn,
        )
    assert conn.committed is False
    assert conn.closed is True
