"""按项目配置执行一条 SQL。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import db  # noqa: E402
from runtime.adapter import AdapterError, load_adapter  # noqa: E402
from runtime.config import ConfigError, load_env, project_dir  # noqa: E402


def main(argv: list[str] | None = None, connect_fn=None) -> int:
    parser = argparse.ArgumentParser(description="按项目配置执行一条 SQL")
    parser.add_argument("--project", required=True)
    parser.add_argument("--env", default="dev")
    parser.add_argument("--db", help="覆盖适配层 database，连同一环境下的其他库")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql")
    source.add_argument("--file", type=Path, help="从文件读取 SQL")
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="执行成功后提交事务；建表、改数据需要，读操作不用",
    )
    args = parser.parse_args(argv)

    if args.commit and args.env == "prod":
        parser.error("prod 只允许只读查询，拒绝 --commit")

    sql = args.file.read_text(encoding="utf-8") if args.file else args.sql

    try:
        adapter = load_adapter(args.project)
    except (AdapterError, ConfigError) as exc:
        print(f"[配置] {exc}")
        return 2
    env = adapter.envs.get(args.env)
    if not env:
        parser.error(f"未知环境 {args.env}")

    prefix = env.get("db_prefix")
    database = args.db or env.get("database")
    if not prefix or not database:
        parser.error(f"环境 {args.env} 缺少 db_prefix 或 database")

    params: dict[str, str] = {}
    for item in args.param:
        key, _, value = item.partition("=")
        params[key] = value

    connect = connect_fn or db.connect
    conn = connect(
        load_env(project_dir(args.project) / ".env"),
        prefix,
        database,
        read_only=not args.commit,
        db_type=env.get("db_type", "postgres"),
    )
    try:
        rows, count = db.execute(conn, sql, params or None)
        if args.commit:
            conn.commit()
    finally:
        conn.close()

    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))
    print(f"{len(rows)} 行，影响 {count} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
