"""PostgreSQL 查询与执行工具。默认只读；dev/test 加 --commit 可执行全部 SQL。prod 始终只读。"""

import argparse
import re
import sys
from pathlib import Path

import psycopg
from psycopg import ClientCursor
from psycopg.rows import dict_row

ENV_FILE = Path(__file__).with_name(".env")
WRITE_ENVS = {"dev", "test"}
WRITE_PATTERN = re.compile(
    r"^\s*(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|merge|call|do|vacuum|analyze|refresh|reindex|cluster|set)\b",
    re.IGNORECASE,
)


def load_env(name: str) -> dict:
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    prefix = name.upper()
    return {
        "host": values[f"{prefix}_HOST"],
        "port": values[f"{prefix}_PORT"],
        "user": values[f"{prefix}_USER"],
        "password": values[f"{prefix}_PASSWORD"],
    }


def connect(env_name: str, dbname: str | None, *, read_only: bool = True):
    conf = load_env(env_name)
    kwargs = {
        "host": conf["host"],
        "port": conf["port"],
        "user": conf["user"],
        "password": conf["password"],
        "dbname": dbname or conf["user"],
        "connect_timeout": 10,
    }
    if read_only:
        kwargs["options"] = "-c default_transaction_read_only=on"
    return psycopg.connect(**kwargs)


def ensure_readonly(sql: str):
    if WRITE_PATTERN.match(sql):
        sys.exit("拒绝执行：本工具只允许只读语句（SELECT / SHOW / WITH / EXPLAIN）。")


def print_rows(rows):
    if not rows:
        print("(0 rows)")
        return
    columns = list(rows[0].keys())
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row[c])))
    print(" | ".join(c.ljust(widths[c]) for c in columns))
    print("-+-".join("-" * widths[c] for c in columns))
    for row in rows:
        print(" | ".join(str(row[c]).ljust(widths[c]) for c in columns))
    print(f"({len(rows)} rows)")


def load_sql(args) -> str | None:
    if args.file and args.sql:
        sys.exit("拒绝执行：--sql 与 --file 只能选一个。")
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return args.sql


def main():
    parser = argparse.ArgumentParser(description="查询或执行 hexincloud PostgreSQL。默认只读；dev/test 加 --commit 可写，prod 始终只读。")
    parser.add_argument("--env", choices=["prod", "test", "dev"], required=True)
    parser.add_argument("--db", help="数据库名，默认与用户名相同")
    parser.add_argument("--sql", help="SQL。不加 --commit 时只允许只读语句")
    parser.add_argument("--file", help="SQL 文件，可含多条语句；须配合 --commit")
    parser.add_argument("--commit", action="store_true", help="dev/test 执行写 SQL 并提交；prod 拒绝")
    parser.add_argument("--list-dbs", action="store_true", help="列出可连接的数据库")
    parser.add_argument("--list-schemas", action="store_true", help="列出当前库的 schema")
    parser.add_argument("--list-tables", metavar="SCHEMA", help="列出指定 schema 的表")
    args = parser.parse_args()

    sql = load_sql(args)
    if args.commit and args.env not in WRITE_ENVS:
        sys.exit("拒绝执行：prod 只允许只读查询。")
    if args.file and not args.commit:
        sys.exit("拒绝执行：SQL 文件必须加 --commit，且只能用于 dev / test。")

    read_only = not args.commit
    with connect(args.env, args.db, read_only=read_only) as conn:
        if read_only:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                if args.list_dbs:
                    cur.execute("select datname from pg_database where not datistemplate order by datname")
                    print_rows(cur.fetchall())
                elif args.list_schemas:
                    cur.execute("select nspname from pg_namespace where nspname not like 'pg\\_%' order by nspname")
                    print_rows(cur.fetchall())
                elif args.list_tables:
                    cur.execute(
                        "select tablename from pg_tables where schemaname = %s order by tablename",
                        (args.list_tables,),
                    )
                    print_rows(cur.fetchall())
                elif sql:
                    ensure_readonly(sql)
                    cur.execute(sql)
                    if cur.description:
                        print_rows(cur.fetchall())
                    else:
                        print("OK")
                else:
                    parser.error("需要 --sql、--file 或 --list-* 参数")
            return

        if not sql:
            parser.error("写执行需要 --sql 或 --file")
        with ClientCursor(conn) as cur:
            cur.execute(sql)
        conn.commit()
        print(f"已提交 {args.env} / {args.db or '(default)'}")


if __name__ == "__main__":
    main()
