"""数据库连接与 SQL 执行。

支持 PostgreSQL 和 MySQL，占位符都用 %(name)s。
"""

from __future__ import annotations

import psycopg
import pymysql

DB_TYPES = ("postgres", "mysql")
MYSQL_READ_ONLY_INIT = "SET SESSION TRANSACTION READ ONLY"


class DbError(Exception):
    pass


def connect(
    env: dict[str, str],
    prefix: str,
    database: str,
    *,
    read_only: bool = False,
    db_type: str = "postgres",
):
    if db_type not in DB_TYPES:
        raise DbError(f"不支持的数据库类型 {db_type}，可选：{'、'.join(DB_TYPES)}")

    keys = {
        "host": f"{prefix}_HOST",
        "port": f"{prefix}_PORT",
        "user": f"{prefix}_USER",
        "password": f"{prefix}_PASSWORD",
    }
    missing = [name for name in keys.values() if not env.get(name)]
    if missing:
        raise DbError(f"{', '.join(missing)} 未配置")

    common = {
        "host": env[keys["host"]],
        "port": int(env[keys["port"]]),
        "user": env[keys["user"]],
        "password": env[keys["password"]],
        "connect_timeout": 10,
    }

    if db_type == "postgres":
        kwargs = {**common, "dbname": database}
        if read_only:
            kwargs["options"] = "-c default_transaction_read_only=on"
        return psycopg.connect(**kwargs)

    kwargs = {
        **common,
        "database": database,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if read_only:
        kwargs["init_command"] = MYSQL_READ_ONLY_INIT
    return pymysql.connect(**kwargs)


def execute(conn, sql: str, params=None) -> tuple[list[tuple], int]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else []
        return rows, cur.rowcount
