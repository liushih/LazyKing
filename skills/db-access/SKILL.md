---
name: db-access
description: >-
  用自然语言查询或修改 PostgreSQL / MySQL 数据库、Redis、MongoDB。用户说「查一下」「连 dev 库」
  「把 X 改成 Y」「看下 redis 的 key」「查 mongo 里的日志」时使用。
  写操作前回显环境与命令，回显不阻塞执行。
---

# 数据库访问

## 适用场景

- SQL：查、查一下、连、SQL、select、count
- MySQL：适配层环境写了 `db_type: mysql` 时，`query.py` 自动连 MySQL，命令与 PostgreSQL 相同
- 修改数据：改、更新、删除、insert、update、delete
- 改结构：建表、加字段、alter、drop table（执行时带上 `--commit`）
- Redis：缓存、key、redis、hash、GET/SET
- MongoDB：mongo、集合、文档、find、aggregate

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet。若提示有新版本：问用户「发现新版本，是否现在更新？」；用户确认后运行 <TOOLS_DIR>/update.ps1。data-tools/、.data-tools/ 和生成的技能入口只在本机使用，按策略不提交进业务仓库；不要提醒用户提交这些改动。用户拒绝则继续，本次会话不再追问。脚本不存在、无新版本、检查失败或 update_check 关闭时继续。

## 前置检查

0. 运行 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> check --capability adapter`。有缺失时用 `project-setup` 补齐；不现场猜个人值，不修改共享 yaml；密钥只提示用户在自己的终端运行 `set-secret`。

1. 读适配层的 `envs.<环境>` 与同目录 `.env`
2. 确认目标环境（dev / test / prod）；用户未说明时问一次
3. 确认存储类型（PostgreSQL / MySQL / Redis / MongoDB）；用户说法不明确时问一次
4. 写操作前回显：环境、库或集合、命令、预计影响范围

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`：从当前目录向上查找；找不到再读 `DATA_TOOLS_DIR`，再找不到读 `~/.data-tools/config.yaml` 的 `tools_dir`；仍找不到就问用户业务仓库根目录，不要猜。`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`：先读 `DATA_TOOLS_HOME`，没有再从当前目录向上查找，最后回退 `~/.data-tools`。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）；没有 venv 时用 `py -3.11` / `py -3` / `python` / `python3`，要求 3.11+；有 Python 但没 venv 时运行 `<TOOLS_DIR>/bootstrap.ps1`。

## 执行

**PostgreSQL**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/query.py" --project <项目ID> --env dev --sql "select status from wms_order where external_order_no = %(no)s" --param no=<单号>
```

同一环境的其他库用 `--db` 指定，例如 `--db hexin_masterdata`。dev、test 允许全部 SQL（查询、插入、更新、删除、建表改表），但必须加 `--commit`：不加时连接是只读的，写语句会被服务器直接拒绝，不是静默丢弃。prod 拒绝 `--commit`。

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/query.py" --project <项目ID> --env dev --db hexin_masterdata --sql "create table tmp_order (id bigserial primary key)" --commit
```

多条语句或直接跑脚本文件，用 `query.py --file`。不加 `--commit` 时仍只读；prod 不能加 `--commit`：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/query.py" --project <项目ID> --env dev --db hexin_masterdata --file path/to/script.sql --commit
```

**MySQL**

适配层 `envs.<环境>` 写 `db_type: mysql`（不写时是 `postgres`），连接键名不变，仍是
`db_prefix` 拼出的 `<prefix>_HOST` / `_PORT` / `_USER` / `_PASSWORD`，库名取 `database`。
命令、`%(name)s` 占位符、`--param`、`--file`、`--commit` 都与 PostgreSQL 相同：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/query.py" --project <项目ID> --env dev --sql "select status from t where no = %(no)s" --param no=<单号>
```

不加 `--commit` 时会话以只读事务打开，写语句会被服务器拒绝；prod 拒绝 `--commit`。

**Redis**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/redis.py" --project <项目ID> --env dev --cmd "GET user:1"
```

**MongoDB**

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/mongo.py" --project <项目ID> --env dev --collection logs --find '{"level": "error"}' --limit 20
```

规则（四种存储通用）：

- 只读：`select`、`GET`/`SCAN`/`HGETALL`、`find`/`aggregate`/`count` 直接执行并返回结果
- 写入：回显后直接执行，不再二次确认
- 破坏性操作（`DROP` / `TRUNCATE` / 无 `WHERE` 的 `DELETE` / `FLUSHDB` / `FLUSHALL` /
  无 filter 的 `delete many`）：额外打印一行警示后照常执行
- SQL 占位符用 `%(name)s`，配合 `--param name=value`；不要拼字符串
- Redis 命令用引号整体传入，如 `--cmd "SET k v"`
- Mongo 参数是 JSON：`--find` 传过滤条件，`--aggregate` 传管道数组，
  `--update` 传 `{"filter": {...}, "update": {...}, "many": true}`
- 连接参数只来自 `.env`，不要在命令行明文传密码
- 事务默认不提交：连接关闭即回滚。**建表、改表、增删改数据必须加 `--commit`**，
  否则语句执行了但不落库；只读查询不加

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺连接配置 | 报键名，引导录入 |
| 连接失败 | 报环境与变量名，不打印密码 |
| SQL 报错 | 原样返回错误，不猜测改写 |
| 影响行数为 0 | 明确报告 0 行，不当作写入成功 |
| 环境未配置 `redis_prefix` / `mongo_prefix` | 报缺的字段名，不尝试默认地址 |
| Redis 返回 nil | 明确说「key 不存在」，不当作空字符串 |

