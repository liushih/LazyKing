import psycopg
import pymysql
import pytest

from runtime.db import DbError, connect, execute


class _Cursor:
    description = ("col",)

    def __init__(self, rows, rowcount):
        self._rows = rows
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, rows, rowcount):
        self._rows = rows
        self._rowcount = rowcount

    def cursor(self):
        return _Cursor(self._rows, self._rowcount)


def test_missing_prefix_key_raises():
    with pytest.raises(DbError, match="DEV_HOST"):
        connect({"DEV_PORT": "5432"}, "DEV", "hexin_wms")


def test_connect_uses_prefixed_keys(monkeypatch):
    seen = {}
    monkeypatch.setattr(psycopg, "connect", lambda **kw: seen.update(kw) or object())
    env = {"DEV_HOST": "h", "DEV_PORT": "5432", "DEV_USER": "u", "DEV_PASSWORD": "p"}
    connect(env, "DEV", "db1")
    assert seen["host"] == "h"
    assert seen["port"] == 5432
    assert seen["user"] == "u"
    assert seen["password"] == "p"
    assert seen["dbname"] == "db1"
    assert seen["connect_timeout"] == 10


def test_execute_returns_rows_and_rowcount():
    conn = _FakeConn(rows=[("A",)], rowcount=3)
    rows, count = execute(conn, "update t set s=%s", ("A",))
    assert rows == [("A",)] and count == 3


def test_connect_read_only_sets_session_option(monkeypatch):
    seen = {}
    monkeypatch.setattr(psycopg, "connect", lambda **kw: seen.update(kw) or object())
    env = {"DEV_HOST": "h", "DEV_PORT": "5432", "DEV_USER": "u", "DEV_PASSWORD": "p"}
    connect(env, "DEV", "db1", read_only=True)
    assert seen["options"] == "-c default_transaction_read_only=on"


def test_connect_writable_omits_read_only_option(monkeypatch):
    seen = {}
    monkeypatch.setattr(psycopg, "connect", lambda **kw: seen.update(kw) or object())
    env = {"DEV_HOST": "h", "DEV_PORT": "5432", "DEV_USER": "u", "DEV_PASSWORD": "p"}
    connect(env, "DEV", "db1", read_only=False)
    assert "options" not in seen


def _mysql_env():
    return {"DEV_HOST": "h", "DEV_PORT": "3306", "DEV_USER": "u", "DEV_PASSWORD": "p"}


def test_mysql_connect_uses_prefixed_keys(monkeypatch):
    seen = {}
    monkeypatch.setattr(pymysql, "connect", lambda **kw: seen.update(kw) or object())
    connect(_mysql_env(), "DEV", "db1", db_type="mysql")
    assert seen["host"] == "h"
    assert seen["port"] == 3306
    assert seen["user"] == "u"
    assert seen["password"] == "p"
    assert seen["database"] == "db1"
    assert seen["charset"] == "utf8mb4"
    assert seen["connect_timeout"] == 10
    assert seen["autocommit"] is False


def test_mysql_read_only_sets_session_transaction_read_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(pymysql, "connect", lambda **kw: seen.update(kw) or object())
    connect(_mysql_env(), "DEV", "db1", read_only=True, db_type="mysql")
    assert seen["init_command"] == "SET SESSION TRANSACTION READ ONLY"


def test_mysql_writable_omits_read_only_command(monkeypatch):
    seen = {}
    monkeypatch.setattr(pymysql, "connect", lambda **kw: seen.update(kw) or object())
    connect(_mysql_env(), "DEV", "db1", read_only=False, db_type="mysql")
    assert "init_command" not in seen


def test_unknown_db_type_raises():
    with pytest.raises(DbError, match="oracle"):
        connect(_mysql_env(), "DEV", "db1", db_type="oracle")
