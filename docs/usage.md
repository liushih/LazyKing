# 使用说明

装好之后，日常用白话触发即可，不需要手写命令。安装步骤见 [README](../README.md)。

> **团队接入的边界**：`data-tools/`、`.data-tools/` 和生成的技能入口只在本机安装，不进入业务仓库 git；团队共享的适配层、坑库和脚本通过公司内网制品库或共享目录分发。详见[第十二节](#十二团队项目接入本机安装不进业务仓库-git)。

## 三分钟上手

1. 新开会话，说「接入 XX 业务」，按提示给接口地址和账号（写进本机 `.env`）
2. 接入跑通后，说「在 dev 造 10 张 XX」
3. 想看结果，说「查一下 dev 库刚才那批」
4. 其他场景直接说：「写本周周报」「提交并推到 dev」

不确定怎么说，看下面第一节的触发词表。细节按需查阅，不必通读。

- [三分钟上手](#三分钟上手)
- [一、八个技能怎么选](#一八个技能怎么选)
- [二、第一次接入业务](#二第一次接入业务)
- [三、适配层写法](#三适配层写法)
- [四、批量造数](#四批量造数)
- [五、结果校验](#五结果校验)
- [六、数据库访问](#六数据库访问)
- [七、坑库](#七坑库)
- [八、配置与路径](#八配置与路径)
- [九、常见问题（安装与接入）](#九常见问题安装与接入)
- [十、写报告](#十写报告)
- [十一、代码托管](#十一代码托管)
- [十二、团队项目接入](#十二团队项目接入本机安装不进业务仓库-git)
- [十三、浏览器测试](#十三浏览器测试)
- [十四、Jenkins 发版](#十四jenkins-发版)

---

## 一、八个技能怎么选

| 意图 | 说法 | 技能 |
|---|---|---|
| 造数 | 造、生成、批量、压测数据、补数据、跑一批 | `data-gen-core` |
| 连库 | 查库、查一下、连、SQL、改数据 | `db-access` |
| 接入 | 接入、新业务、第一次、打通、适配 | `adapter-bootstrap` |
| 浏览器测试 | 测一下、走一遍、浏览器验证、点一遍、复现、回归 | `browser-test` |
| 报告 | 日报、周报、月报、述职、汇报材料 | `report-writer` |
| 代码托管 | 提交、推送、合并、建 MR、开分支、热修 | `git-workflow` |
| 发版 | 发版、构建、部署、Jenkins | `jenkins-deploy` |
| 个人配置 | 初始化个人配置、新同事接入、配置我的账号 | `project-setup` |
| 沉淀 | 记下来、加到坑里、更新规则 | 写 `pitfalls.md` |

同时命中多个时按这个顺序：

1. 含「接入 / 新业务」→ 走接入，即使同时提到造数
2. 含「日报 / 周报 / 月报 / 述职」→ 写报告
3. 含「提交 / 推送 / 合并 / 建 MR / 开分支 / 热修」→ 代码托管
4. 含「发版 / 构建 / 部署 / Jenkins」→ Jenkins 发版
5. 含「测一下 / 走一遍 / 浏览器 / 页面 / 复现 / 回归」→ 浏览器测试
6. 有造数动词且带业务名词 → 批量造数
7. 只有动词没有名词（「造点数据」）→ 追问是哪个业务
8. 有 SQL 关键字或表名 → 数据库访问
9. 都不命中 → 直说没听懂，不猜

## 二、第一次接入业务

### 先准备什么

接入前准备两类个人配置：非敏感值（账号、本机路径、作者）写 `personal.yaml`，密码、令牌和数据库连接键写 `.env`；两者都不进任何 git。团队共享的 `adapter.yaml` 只写团队地址和 `${VAR}`，通过内网制品库或共享目录分发。

| 配置 | 用途 | 必需 | 权限 |
| --- | --- | --- | --- |
| 系统登录账号 | 调接口造数 | 是 | 能执行目标业务操作即可 |
| 数据库连接 | `verify` 校验结果 | 否 | 只读 |

`adapter.yaml` 里的 `${VAR}` 必须能在 `personal.yaml` 或 `.env` 找到。典型个人文件：

```yaml
# personal.yaml（不提交）
ACME_USERNAME: your-account
```

```dotenv
# .env（不提交）
ACME_PASSWORD=
# 数据库：DEV 对应 adapter 里 envs.dev.db_prefix
DEV_HOST=
DEV_PORT=
DEV_USER=
DEV_PASSWORD=
```

`db_prefix: DEV` 会拼出 `DEV_HOST` / `DEV_PORT` / `DEV_USER` / `DEV_PASSWORD`；
test、prod 环境同理换成 `TEST_` / `PROD_`。数据库连接键由 `db-access` 直接读 `.env`，所以留在 `.env`。

两点建议：

- 接口账号用目标环境（dev/test）的，别拿生产账号造数
- 数据库账号给只读，`verify` 只查不写；生产环境尤其不要带写权限

数据库可以先不配。没有它照样能造数，只是 `verify` 段不生效，只能确认流程走完，
确认不了数据最终状态。

### 接入流程

新业务第一次造数前，必须先有适配层。直接说「接入 XX 业务」即可，技能会：

1. 确认项目 ID 与数据目录
2. 收集接口地址、认证方式、目标状态
3. 逐项确认字段映射、枚举取值、异步时序
4. 起草 `adapter.yaml`，先跑 1 条
5. 失败就查接口或问你，不猜字段
6. 跑通后补 `verify` 段
7. 把踩到的坑写进 `pitfalls.md`

产出在 `<DATA_HOME>` 下：

```
<DATA_HOME>\projects\<项目ID>\
├── adapter.yaml      业务规则
├── .env              接口地址与账号（不进 git）
├── .env.example      键名模板（只留本机，不含值）
├── pitfalls.md       踩坑记录
├── scripts\          需要代码才能做的步骤
└── ledger.csv        运行台账（第一次跑数后生成）
```

`<DATA_HOME>` 在业务仓库里是仓库根目录的 `.data-tools\`；个人全局使用时是
`%USERPROFILE%\.data-tools\`。解析顺序见[第八节](#八配置与路径)。

接入完成后，之后每次造数都直接复用这份规则。

## 三、适配层写法

### 顶层结构

```yaml
version: 1
project: hexincloud

envs:
  dev:
    base_url: ${HEXIN_BASE_URL}   # 值只写在同目录 .env
    db_prefix: DEV                # 对应 .env 的 DEV_HOST / DEV_PORT / ...
    database: hexin_wms           # 校验时连的库

auth:
  type: none                      # none | custom

entities:
  b2d_pickup_order:
    description: B2D 提货单
    stop_at: UPLOADED
    id_rule: "PB{run_id}{idx:04d}"
    steps:
      - id: create
        call: POST /order/create
        body:
          "externalNo": ${ctx.external_no}
      - id: wait_packages
        poll: GET /order/status
        until: "resp.get('customsMode') != None"
        timeout: 60
    verify:
      sql: "select status from t where no = %(no)s"
      expect: UPLOADED
```

### 步骤的三种类型

`call`、`poll`、`impl` 必须且只能有一个。

| 类型 | 行为 | 失败条件 |
|---|---|---|
| `call` | 发一次请求，结果存进 `ctx.values[<id>]` | HTTP ≥ 400，或网络重试耗尽 |
| `poll` | 循环请求直到 `until` 为真 | 超过 `timeout` 秒 |
| `impl` | 调 `<项目目录>/<文件>:<函数>`，函数签名 `func(ctx, None)` | 文件或函数不存在、函数抛错 |

`until` 是 Python 表达式，可用 `resp` 和 `ctx`。

### 变量替换

| 写法 | 含义 |
|---|---|
| `${ctx.external_no}` | 当前单号 |
| `${prev.create.orderId}` | 某一步的产出字段 |

整个字符串就是一个引用时保留原类型（数字、对象）；否则按字符串拼接。

`body` / `params` 的键名要加引号。YAML 会把 `no`、`yes`、`on`、`off` 解析成布尔，
写成 `no:` 实际是 `false:`，加载时会直接报错提示。

`before` 列出的步骤必须在同一个 `entities` 下先声明，且只会执行一次。

完整的字段表见 `skills/_references/adapter-contract.md`，模板见
`skills/_TEMPLATE/adapter.example.yaml`。

## 四、批量造数

```bash
.venv/Scripts/python.exe scripts/run.py --project hexincloud --entity b2d_pickup_order \
  --count 100 --workers 5 --run-id 1026a
```

| 参数 | 说明 |
|---|---|
| `--count` | 数量，默认 1 |
| `--workers` | 并发数，默认 1 |
| `--run-id` | 批次号；不填按时间生成，例如 `1026114054` |
| `--env` | 环境，默认 `dev` |

### 台账

每次运行往 `<项目目录>\ledger.csv` 追加：

```
run_id,idx,external_no,stage,status,error,updated_at
1026a,0,PB1026a0000,chain,done,,2026-10-26 11:43:55
```

- `stage` 是失败时停留的步骤名
- `error` 写入前会脱敏，令牌不会落盘

### 断点续跑

用同一个 `--run-id` 重跑，`status=done` 的单会被跳过，只补失败和没跑到的。

```bash
.venv/Scripts/python.exe scripts/run.py --project hexincloud --entity b2d_pickup_order \
  --count 100 --workers 5 --run-id 1026a
```

### 失败处理

- 单条失败不影响其他单，退出码为 1
- 写请求（POST/PUT）超时不重试，避免重复建单
- 读请求超时自动重试 2 次
- 业务接口报错时，先查 `pitfalls.md` 有没有同现象

## 五、结果校验

适配层里写 `verify`，`run.py` 每单跑完自动执行：

```yaml
verify:
  sql: "select status from t where no = %(no)s"
  expect: UPLOADED
```

- 占位符用 `%(no)s`，值是单号
- 结果与 `expect` 不一致 → 这单记为 failed
- 没写 `verify` 就不会校验，只按流程是否走完记 done

数据库连接用 `envs.<环境>` 的 `db_prefix`（找 `.env` 里的 `DEV_HOST` 等）
和 `database`。校验跑在项目自己的 `.env` 上，与 `hexin-db-tools/.env` 无关。

## 六、数据库访问

数据库查询支持四种存储：PostgreSQL 和 MySQL 共用 `query.py`，Redis、MongoDB 各有入口。
配置都在项目 `.env`。

**PostgreSQL**

```bash
.venv/Scripts/python.exe scripts/query.py --project hexincloud --env dev \
  --sql "select delivery_no, delivery_status from wms_delivery_order order by id desc limit 3"
```

带参数时用 `%(name)s` 配合 `--param`，不要拼字符串：

```bash
.venv/Scripts/python.exe scripts/query.py --project hexincloud --env dev \
  --sql "select status from t where external_order_no = %(no)s" --param no=PB1026114338
```

直接执行 SQL 文件（支持多语句）：

```bash
.venv/Scripts/python.exe scripts/query.py --project hexincloud --env dev \
  --db hexin_masterdata --file path/to/script.sql --commit
```

`--sql` 与 `--file` 互斥；不加 `--commit` 时仍只读，prod 不允许 `--commit`。

**MySQL**

适配层 `envs.<环境>` 加 `db_type: mysql`（不写时是 `postgres`），连接键名不变，
仍是 `db_prefix` 拼出的 `DEV_HOST` / `DEV_PORT` / `DEV_USER` / `DEV_PASSWORD`，
库名取 `database`：

```yaml
envs:
  dev:
    db_prefix: DEV
    database: acme_shop
    db_type: mysql
```

`query.py` 的用法与 PostgreSQL 完全相同：`%(name)s` 占位符、`--param`、`--file`、
`--commit`。不加 `--commit` 时会话以只读事务打开，写语句会被服务器拒绝；
prod 不允许 `--commit`。`run.py` 的 `verify` 也按同一个 `db_type` 连接。

**Redis**

```bash
.venv/Scripts/python.exe scripts/redis.py --project hexincloud --env dev --cmd "GET user:1"
.venv/Scripts/python.exe scripts/redis.py --project hexincloud --env dev --cmd "SCAN 0 MATCH order:* COUNT 50"
.venv/Scripts/python.exe scripts/redis.py --project hexincloud --env dev --cmd "HGETALL cfg:warehouse"
```

**MongoDB**

```bash
.venv/Scripts/python.exe scripts/mongo.py --project hexincloud --env dev \
  --collection logs --find '{"level": "error"}' --limit 20

.venv/Scripts/python.exe scripts/mongo.py --project hexincloud --env dev \
  --collection logs --aggregate '[{"$group": {"_id": "$level", "n": {"$sum": 1}}}]'

.venv/Scripts/python.exe scripts/mongo.py --project hexincloud --env dev \
  --collection logs --update '{"filter": {"_id": "x"}, "update": {"$set": {"a": 1}}}'
```

规则（四种通用）：

- 只读（`select`、`GET`/`SCAN`/`HGETALL`、`find`/`aggregate`/`count`）直接执行
- 写操作先回显环境、目标、命令，回显后直接执行，不再二次确认
- `DROP` / `TRUNCATE` / 无 `WHERE` 的 `DELETE` / `FLUSHDB` / `FLUSHALL` /
  无 filter 的批量删除，额外打印一行警示
- 影响行数为 0 或 key 不存在，明确报告，不当作成功
- 默认只读连接：建表、改表、增删改数据必须加 `--commit`，否则写语句会被服务器直接拒绝；prod 不允许 `--commit`

命令行要跟一句「只读」或「可以写」，权限完全按你的口令走。

**配置键名**

```
DEV_REDIS_HOST / DEV_REDIS_PORT / DEV_REDIS_PASSWORD / DEV_REDIS_DB
DEV_MONGO_URI
```

`adapter.yaml` 的 `envs.dev` 里写 `redis_prefix: DEV_REDIS`、`mongo_prefix: DEV_MONGO`、
`mongo_database: <库名>`。MySQL 与 PostgreSQL 共用 `db_prefix` 拼出的
`<prefix>_HOST` 等键，只额外写 `db_type: mysql`。缺哪个键会直接报出来，不会回退到默认地址。

## 七、坑库

`pitfalls.md` 只追加，不删除。每条四段：

```markdown
### P1 建单前必须先取 stageToken

- 现象：直接传 items 建单，返回「工作区已过期」
- 原因：建单前必须先调 item-stage/items 获取 stageToken
- 绕法：先取 token，再带 token 提交 items
- 适用：create 步骤
```

什么时候写：

- 某次运行失败，查明原因并绕过之后
- 发现了枚举取值、异步时序这类不明显的行为
- 用户说「记下来」

写入前先读现有条目，按「现象」去重。下次造同类数据时，技能会先读这份坑库，不重复试错。

## 八、配置与路径

**工具包**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATA_TOOLS_DIR` | `~/.data-tools/config.yaml` 的 `tools_dir` | 技能定位执行入口 |
| `DATA_TOOLS_HOME` | 项目内 `.data-tools/`，没有则 `%USERPROFILE%\.data-tools` | 适配层、台账、坑库、凭据 |

`<DATA_HOME>` 按顺序解析：`DATA_TOOLS_HOME` > 从当前目录向上找到的最近一个
`.data-tools/` > `%USERPROFILE%\.data-tools`。在业务仓库里默认用仓库自己的
`.data-tools/`，所以团队规则和坑库默认在本机；按策略不提交业务仓库 git，
团队共享通过内网制品库或共享目录分发。设置了 `DATA_TOOLS_HOME` 则以它为准。

**旧工具（`hexin-db-tools/`、`hexin-data-gen/`、`hexin-e2e/`）**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HEXIN_REPO` | `..\hexincloud` | 业务主仓库位置 |
| `HEXIN_DB_ENV` | `hexin-db-tools\.env` | 三环境库账号文件 |
| `HEXIN_SKILL_SCRIPTS` | `$HEXIN_REPO\dev-overlay\...\scripts` | 飞书台账脚本 |
| `PW_PROFILE` | `..\pw-profile` | 浏览器登录态 |

`setup.ps1` 会把仓库路径写进 `config.yaml`。仓库换位置后重跑一次 `setup.ps1`，
或者设置 `DATA_TOOLS_DIR`。

## 九、常见问题（安装与接入）

**技能装好了但列表里没有**

Claude Code 的插件内容在启动时加载。装完或更新后重启一次应用。
仍然没有时检查 `%USERPROFILE%\.claude\plugins\installed_plugins.json` 里有没有
`data-tools@data-tools`，以及 `cache\data-tools\data-tools\<版本>\` 目录是否存在。

DSH 没有插件市场，走 `install.ps1 -Target dsh` 直接写 `%USERPROFILE%\.dsh\skills\`，
装完新开会话就生效。列表里没有时确认文件落在 `<技能名>\SKILL.md`，不要多套一层目录。

**DSH 里造数写台账报「访问被拒绝」**

DSH 的 `workspace-write` 沙箱只允许写工作区和临时目录。个人/全局模式下
`<DATA_HOME>` 是 `~/.data-tools`，在工作区外；把 `DATA_TOOLS_HOME` 指到工作区内
（如 `<仓库>/.data-tools`），或让会话用完全访问权限。团队模式的数据目录本来就在
业务仓库内（但不进 git），不受影响。只读查询不受影响。

**改了技能规则但不生效**

同上，重启后才会读到新内容。

**提示 No module named 'xxx'**

先跑一次 `setup.ps1`，或手动 `pip install -r requirements.txt`。
插件缓存里没有虚拟环境，依赖装在 clone 下来的仓库里。

**提示找不到工具目录**

检查 `%USERPROFILE%\.data-tools\config.yaml` 的 `tools_dir`，或设置 `DATA_TOOLS_DIR`。

**提示缺少个人配置**

运行 `data-tools/scripts/config.py --project <项目ID> check`，按提示运行 `project-setup` 生成 `personal.yaml` 与 `.env`；不要修改共享 yaml。

**业务接口报 token 无效**

项目内模式删掉 `.data-tools/projects/<项目ID>/.token.json` 后重跑；旧工具模式删 `hexin-data-gen\.token.json`。会重新登录。

**返回「未定义变量 X」**

适配层里用了 `${X}`，但同目录 `.env` 没有 `X`。补上或改正名字。

**返回「含非字符串键」**

YAML 把 `no` / `yes` / `on` / `off` 解析成了布尔。给键加引号，写成 `"no":`。

**批量跑完一半失败**

用同一个 `--run-id` 重跑，已完成的不再重复。

**数据库连不上**

`db-access` 用的是项目目录下的 `.env`，需要 `DEV_HOST` / `DEV_PORT` /
`DEV_USER` / `DEV_PASSWORD`（对应环境是 TEST_ / PROD_）。这些跟
`hexin-db-tools/.env` 是两套文件，不会自动同步。

**提交前自查敏感信息**

```bash
.venv/Scripts/python.exe scripts/check_secrets.py
```

只扫已跟踪文件，检查明文凭据、GitHub 令牌、私钥和私网地址。

## 十、写报告

### 说法与类型

| 类型 | 说法 | 时间范围 |
|---|---|---|
| 日报 | 写今天的日报 | 当天 |
| 周报 | 出本周周报 | 周一至周日 |
| 月报 | 写这个月的月报 | 自然月 |
| 述职 | 生成 Q3 述职 | 你指定 |

四种报告各自从原始数据生成，周报不汇总日报，月报不汇总周报。

### 生成前会问什么

1. **项目**：你说了就用；没说就按当前工作目录匹配；对不上或命中多个会问，不猜
2. **受众**：直属领导（默认）/ 更高层 / 自己留痕 / 团队共享。选择记在
   `reports/<项目ID>/.audience`，下次直接回车沿用
3. **角色**（述职必问）：开发 / 测试 / 产品 / 其他。记在 `reports/<项目ID>/.role`，
   当次口头指定优先于记忆值
4. **补充**：先报数据（几个提交、几个任务、几个 Bug），再问「有什么没体现在提交和工单里的」

受众决定语气，角色决定重点：

| 角色 | 重点 | 指标 |
|---|---|---|
| 开发 | 交付、质量、技术债 | 提交、修复 Bug、线上问题 |
| 测试 | 覆盖、缺陷拦截、质量门禁 | 发现 Bug、用例覆盖、漏测 |
| 产品 | 需求价值、上线节奏、用户指标 | 需求交付数、验收通过率 |

角色只影响写法。测试角色关心的「我发现的 Bug」目前采集不到，写述职时会向你要，
或者明确标注「本次未统计发现类缺陷」。真要自动采集，需要按角色扩展禅道查询。

### 配置

`<DATA_HOME>/projects/<项目ID>/report.yaml`：

```yaml
git:
  repos: ${REPORT_REPOS}
  authors: ${GIT_AUTHORS}
zentao:
  api: auto          # auto | v1 | v2，当前实现 v2
  base_url: http://zentao.example.com   # 团队共用地址
  account: ${ZENTAO_ACCOUNT}
  password: ${ZENTAO_PASSWORD}
  product_id: 31
  project_ids: [73]
  authors: ${ZENTAO_AUTHORS}
```

`REPORT_REPOS`、`GIT_AUTHORS`、`ZENTAO_ACCOUNT`、`ZENTAO_AUTHORS` 在本机 `personal.yaml`；`ZENTAO_PASSWORD` 在 `.env`，与适配层共用。禅道 token 缓存在 `~/.zentao-token.json`，登录一次后复用。

### 报告存在哪

```
<DATA_HOME>/reports/<项目ID>/
├── 2026-10-26-daily.md
├── 2026-W44-weekly.md
├── 2026-10-monthly.md
└── 2026-Q3-review.pptx
```

按周期命名，同一周期重跑直接覆盖。汇总数据临时放在同目录 `.collect/` 下。

### 输出 Word / PPT

Markdown 是唯一内容源，Word 和 PPT 都从它渲染：

```bash
.venv/Scripts/python.exe scripts/render.py --input <md> --format docx,pptx --out-dir <目录>
```

### 模板

`<DATA_HOME>/templates/<项目ID>/<类型>.md`，只定义章节和提示语：

```markdown
## 本周完成
<!-- 写结果，不写过程；按业务主题分组 -->

## 数据支撑
<!-- 提交数、完成任务数、修复 bug 数 -->
```

没有模板时用内置结构：日报「今日完成 / 明日计划 / 风险」，周报「本周完成 / 关键数据 /
问题与风险 / 下周计划」，月报「目标达成 / 关键成果 / 问题与改进 / 下月重点」，
述职「成果 / 问题与反思 / 规划」。

### 数据缺失

禅道连不上或未授权时，报告仍然生成，但开头会写「禅道数据缺失，本次仅基于代码提交」。
某个仓库路径不存在时同样跳过并提示，不会静默少一块。

## 十一、代码托管

支持 GitHub、Gitee、GitLab。令牌放在项目 `.env` 里，工具只按键名读取，不会出现在命令行、日志或报告中。

### 配置

`<DATA_HOME>/projects/<项目ID>/git_hosts.yaml`：

```yaml
user_tag: ${USER_TAG}         # 个人标识，在 personal.yaml
repo_path: ${REPO_PATH}       # 本机仓库路径，在 personal.yaml
host:
  kind: gitlab                # github | gitee | gitlab
  base_url: http://git.example.com   # GitHub、Gitee 可省略，使用平台默认地址
  project_path: group/demo    # GitLab 为 group/project；GitHub、Gitee 为 owner/repo
  token_key: GITLAB_TOKEN_DEMO       # 对应项目 .env 中的键名
branches:
  dev: dev
  test: test
  prod: prod
rules:
  forbid_commit_paths:        # 本地环境配置不提交
    - pom.xml
    - vite.config.ts
```

项目 `.env` 中填写令牌：

```dotenv
GITLAB_TOKEN_DEMO=
```

`set-user-tag` 只写 `personal.yaml`；共享 `git_hosts.yaml` 保持占位符。

### 常用命令

```bash
.venv/Scripts/python.exe scripts/git_host.py --project demo set-user-tag lsh
.venv/Scripts/python.exe scripts/git_host.py --project demo branch create --name feature/test/lsh/1234-描述 --target test
.venv/Scripts/python.exe scripts/git_host.py --project demo commit -m "feat-1234: 描述

正文说明本次修改。"
.venv/Scripts/python.exe scripts/git_host.py --project demo push --branch feature/test/lsh/1234-描述
.venv/Scripts/python.exe scripts/git_host.py --project demo sync
.venv/Scripts/python.exe scripts/git_host.py --project demo mr create --from feature/test/lsh/1234-描述 --to test --title "标题"
.venv/Scripts/python.exe scripts/git_host.py --project demo merge --from feature/test/lsh/1234-描述 --to dev
.venv/Scripts/python.exe scripts/git_host.py --project demo push --branch dev
.venv/Scripts/python.exe scripts/git_host.py --project demo verify-flow --prod-branch prod --test-branch feature/test/lsh/1234-描述 --target dev
.venv/Scripts/python.exe scripts/git_host.py --project demo hotfix sync --fix-branch feature/prod/lsh/1234-热修 --task 1234
```

### 规则

工具会在执行前检查这些规则，违反则拒绝并给出规则名：

| 规则名 | 含义 |
|---|---|
| `branch-naming` | 分支名须为 `feature/<目标>/<用户标识>/<任务号>-<描述>`，且用户标识与配置一致 |
| `commit-message` | 首行须为 `feat-<任务号>: <描述>` 或 `fix-<任务号>: <描述>`，且必须有正文 |
| `forbidden-path` | 禁止提交 `forbid_commit_paths` 中的文件 |
| `direct-merge` | 合到 test、prod 只能建 MR，不能本地合并 |
| `prod-derived` | prod 衍生分支不能直接合到 test 或 dev，要先经过 test 衍生的同步分支 |
| `net-increment` | 合到 dev 时若带入了非本分支的内容，先列清单，确认后加 `--confirm-bring-in` |
| `push-target` | 本地分支名为 test、prod 时不能推送（只能走 MR）；dev 允许直接推送；其余分支只推到同名远端分支 |
| `sync-source` | `sync` 只能同步分支名中「目标」对应的 origin 分支，如 `feature/test/...` 只能同步 test，不能同步 dev。分支名不完整时按 `feature/<目标>/` 前缀判断；没有目标前缀时用 `--from` 指定来源 |

分支名只允许一个任务号，因此「一分支一任务」由分支名格式保证。

### 分支从哪里切

- **默认从 `origin/test` 切**：新任务、缺陷修复、迭代需求一律以 test 最新基线为准
- 仅当用户明确要求「只进 dev、不经 test」时，从 `origin/dev` 切
- 热修复：从 `origin/prod` 切，之后按热修复流程同步

`branch create` 从 `origin/<目标>` 切出，不跟踪上游，切完会核对起点与目标一致。

`sync` 的来源默认取当前分支名的 `feature/<目标>/` 前缀；任务号等后半段不规范也能同步，前缀缺失时才需要用 `--from` 指定。

### 标准提交流程

1. 提交（`commit`），工作区已跟踪文件必须干净
2. 若同时要进 dev：先 `merge --to dev`，再 `push --branch dev`（顺序见下）
3. 若要进 test：`sync` 把最新 `origin/test` 合进当前分支，有冲突先解决，再 `push`，最后 `mr create --to test`

`merge --to dev` 先 fetch，并以 `origin/dev` 为准预检；本地 dev 落后会先快进，已分叉则停止，不强行覆盖。
先合 dev、后 `sync` test，避免把送测期间新增的改动一并带入 dev。

冲突时 `sync` 与 `merge` 会保留现场并列出冲突文件，不会自动解决，也不会 abort。解决冲突须保留双方改动，禁止整文件取一边。
解决后执行 `git add <文件>` 与 `git commit --no-edit`；放弃则执行 `git merge --abort`。

### 热修复流程

1. 从 `origin/prod` 切热修复分支，修复，提交
2. 热修复分支开 MR 到 prod
3. 从 `origin/test` 切同步分支，执行 `hotfix sync`，用 cherry-pick 搬热修复的提交
4. 同步分支开 MR 到 test
5. 同步分支合到 dev 前，用 `verify-flow` 核对，确认只带入热修复的改动

遇到 MR 冲突或 cherry-pick 冲突，工具会停止并列出冲突文件，不会自动解决（cherry-pick 冲突会中止；`sync`、`merge` 冲突则保留现场）。

## 十二、团队项目接入（本机安装，不进业务仓库 git）

把整套工具同步到业务仓库的本机副本，但 `data-tools/`、`.data-tools/` 和生成的技能入口都不会进入业务仓库 git。业务仓库只保留业务代码；个人全局安装方式仍然有效，两种方式互不影响。

### 目录布局

维护者在 LazyKing 仓库运行同步脚本：

```bash
python scripts/sync_project.py --project-dir C:\project\<业务仓库> --project-id <项目ID> --targets claude
```

`--targets` 可选 `claude,cursor,dsh`，逗号分隔，默认 `claude`。codex 只能写 `AGENTS.md`，无法局部忽略，因此团队模式不生成。
不加 `--project-id` 时仍会创建 `.data-tools/` 根目录并同步工具包，只跳过
`.data-tools/projects/<项目ID>/` 的项目骨架。

业务仓库本地会出现：

```text
<业务仓库>/
├── data-tools/                        # 本机安装，不提交
│   ├── skills/                        # 规则源
│   ├── runtime/
│   ├── scripts/
│   ├── requirements.txt
│   ├── bootstrap.ps1                  # 首次接入与环境检查
│   ├── update.ps1                     # 版本检查与一键更新
│   ├── README.md                      # 同事接入说明（模板渲染）
│   ├── LICENSE
│   ├── VERSION                        # 版本、源 commit、同步时间
│   └── .venv/                         # 本机生成，不提交
├── .claude/skills/                    # 生成的技能入口，不提交（仅 data-tools 技能目录）
└── .data-tools/                       # 本机数据根，不提交
    ├── config.yaml                    # default_project
    ├── templates/<项目ID>/            # 报告模板（可选）
    ├── reports/                       # 报告产物
    └── projects/<项目ID>/
        ├── adapter.yaml               # 业务规则
        ├── pitfalls.md                # 坑库
        ├── report.yaml                # 报告配置（可选，团队事实 + 占位符）
        ├── git_hosts.yaml             # 代码托管配置（可选，团队事实 + 占位符）
        ├── jenkins.yaml               # 发版配置（可选，团队事实 + 占位符）
        ├── personal.example.yaml      # 个人键清单
        ├── personal.yaml              # 本人个人值
        ├── scripts/                   # impl 步骤代码、复杂业务模块
        ├── .env.example               # 密钥键名模板
        └── .env                       # 各人密钥
```

复杂业务的 impl 模块（如 `chain.py`、`hexin_client.py`）也放在 `projects/<项目ID>/scripts/`，只在本机使用；团队共享通过内网制品库或共享目录分发，不要提交进业务仓库。B2D/B2C 已内置，不再依赖旧 `hexin-data-gen`/`hexin-db-tools`。

同步工具会把 `/data-tools/`、`/.data-tools/` 和生成的技能目录整体写进业务仓库 `.gitignore`。如果业务仓库之前已经提交过这些路径，同步工具会提示用 `git rm -r --cached` 移出版本库，本地文件保留。不要用 `git add -f` 绕过；团队共享走内网制品库或共享盘。

### 同事第一次接入

1. 从团队内网制品库或共享盘拿到 `data-tools/`，放到业务仓库根目录（不要提交）
2. 在仓库根目录运行：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\data-tools\bootstrap.ps1
   ```

   脚本检查 Python 3.11+，创建 `data-tools/.venv`、升级 pip、安装
   `requirements.txt`。幂等：`.venv` 已存在时只补装依赖。需要同时创建项目目录时
   加 `-ProjectId <项目ID>`。

3. 打开 AI 工具，新开会话，说「初始化个人配置」，按 `project-setup` 的提示生成 `personal.yaml` 与 `.env`
4. 直接说「造 100 张提货单」

`data-tools/`、`.data-tools/`、生成的技能入口都不提交；`personal.yaml` 与 `.env` 只留本机。团队共享 yaml 不要写个人值。

技能每次启动会先做环境检查：解释器优先用 `data-tools/.venv`，没有 venv 但有
Python 3.11+ 时提示运行 `bootstrap.ps1`；同时用 `update.ps1 -CheckOnly -Quiet`
顺带看一眼版本。有新版本时会先问是否现在更新，确认后才运行 `update.ps1`；
拒绝则继续本次会话，不再追问。

### 更新

在业务仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\data-tools\update.ps1
```

更新会重新运行同步脚本：刷新本机的 `data-tools/`（含 `README.md`、`LICENSE`、`VERSION`），
重新生成已启用的技能入口（`.claude/skills/`、`.cursor/rules/`、`.dsh/skills/`
中实际存在的那几种），并刷新业务仓库 `.gitignore` 的 `# data-tools:begin` 块。
`.data-tools/` 里已有的项目数据不覆盖（缺 `.env.example` 时会补模板），也不会自动提交。
更新只改本机副本；不需要提交任何 data-tools 变更。

`-CheckOnly` 只检查不更新，有新版本时退出码为 10；`-Quiet` 配合它使用，
没有新版本时不输出。更新源默认是 `https://github.com/liushih/LazyKing.git`，
可以在 `.data-tools/config.yaml` 的 `data_tools.source` 改。同一段还可以设置：

- `update_check: false`：彻底关闭更新检查
- `check_interval_hours`：成功检查的缓存时长，默认 24 小时
- `failure_cooldown_minutes`：失败后的冷却时长，默认 15 分钟

### 常见问题

**提示「未找到 Python 3.11 或更高版本」**

bootstrap 和 update 都会先找 Python。到 <https://www.python.org/downloads/> 安装
Python 3.11+，安装时勾选 **Add python.exe to PATH**，然后重跑脚本。脚本不会代装，
也不修改系统 PATH。

**`data-tools` 已被 git 跟踪，更新被拒绝**

`update.ps1` 会先检查 `data-tools/` 是否还在 git 索引里。如果旧版本曾经提交过，
先运行 `git rm -r --cached -- data-tools` 并提交这次删除（本地文件会保留），
再重新运行更新。按新策略，`data-tools/`、`.data-tools/` 和生成的技能入口都不进业务仓库 git。

**更新时提示「克隆更新源失败」**

更新需要访问配置的 `source` 仓库。检查网络、代理和 Git 凭据后重试；
检查失败后会按 `failure_cooldown_minutes`（默认 15 分钟）冷却，之后自动重试，
不会每次技能启动都卡在网络上。想彻底关闭检查，在 `.data-tools/config.yaml` 的
`data_tools` 段设置 `update_check: false`。用本地路径或内网镜像时，改
`.data-tools/config.yaml` 的 `data_tools.source`。

**`data-tools/.venv` 存在但 Python 不可用**

bootstrap 会提示删除或重命名 `data-tools/.venv` 后重跑，重新创建虚拟环境。

## 十三、浏览器测试

用本机 Chrome 打开前端页面，按步骤操作并核对结果。第一次由 AI 看着页面把步骤写成流程文件，之后同样的测试直接复跑，不用再重新找入口和选择器。

### 接入一个项目

1. **确认环境**：本机装了 Chrome 和 Python 3.11+，已按「团队项目接入」或「快速开始」装好 data-tools。
2. **配置前端地址和登录**：在 `.data-tools/projects/<项目ID>/browser/browser.yaml` 里写各环境的前端根地址（不是接口地址）、登录步骤和登录成功的判断，模板见 `skills/_TEMPLATE/browser.example.yaml`。地址写团队实际值或 `${变量}`，账号与密码写 `${变量}`。
3. **填变量**：前端根地址直接在 `browser.yaml` 写团队地址；登录账号写 `personal.yaml`，密码写 `.env`。新增键时按是否密钥更新 `personal.example.yaml` 或 `.env.example`。
4. **检查**：运行 `browser.py doctor --project <项目ID>`，确认 Chrome、依赖、配置和变量都齐全。
5. **生成第一个流程**：对 AI 说「测一下 XX 页面」。没有现成流程时，AI 会先用 `probe` 看一遍页面，再把入口、步骤、断言写成 `browser/flows/<名称>.yaml`，并跑到通过。
6. **只留本机**：流程写完不加入 git，截图、诊断包、浏览器 profile 在 `.data-tools/browser/` 也不会加入。`data-tools/`、`.data-tools/` 和生成的技能入口按策略整体不进业务仓库 git；团队共享通过内网制品库或共享目录分发。

### 日常使用

直接说：

| 你说 | 它做 |
|---|---|
| 测一下 B2D 待发货 | 复跑已有的 `b2d-send` 流程 |
| 浏览器验证一下这个单号 | 把单号作为参数传给流程再跑 |
| 走一遍修改物流方式 | 按流程点击并核对 |
| 页面改了，流程挂了 | 读失败诊断，改流程后重跑 |

也可以自己用命令：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" list --project <项目ID>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" run --project <项目ID> --flow <名称> --var order_no=<单号>
```

| 选项 | 说明 |
|---|---|
| `--var 名称=值` | 传流程参数，可重复 |
| `--env dev` | 指定环境，不写用默认环境 |
| `--headed` | 本次显示浏览器窗口（一次性启动，会先关掉后台常驻的那个）；平时不需要 |
| `--profile 路径` | 换一个浏览器 profile，用于强制重新登录 |

其余命令：`doctor` 检查环境，`probe --url <页面>` 探索一个新页面，`stop` 关闭后台常驻浏览器，`clean` 清理运行产物与浏览器缓存。登录状态保存在固定的 profile 里，第二次起不用重新登录。

运行产物不用手动收拾：报告保留最近 20 份，诊断包和探索快照各保留 10 份、最多 7 天；`--trace` 只在失败时随诊断包保留。每次测试开始时会自动清理旧产物，同一流程通过时还会立即删掉它之前的失败诊断包。测试做完、不再需要诊断时运行 `browser.py clean --project <项目ID>`，会清空全部诊断包、探索快照和 trace，并删除 Chrome 的缓存目录（登录态保留）；加 `--all` 清理本机所有 profile。

### 浏览器在后台常驻

测试默认用一个**专用的无头 Chrome**，不弹窗，不会打扰你办公：

- 第一次跑流程时自动在后台拉起，之后每次测试都连上这个已经开着的浏览器，跑完只断开、不关。不用每次重新启动，也省掉重复的启动时间。
- 它是工具自己开的专用实例，用工具自己的 profile，**不会碰你日常使用的 Chrome**，也不接管你的标签页。
- 你重启电脑或手动把它关了，下一次测试会自动重新拉起。
- 想看页面时，加 `--headed` 单次开窗口；跑完它自己关，下次测试再回到后台常驻。
- 不再需要时用 `stop` 关掉（会顺手清掉该 profile 的 Chrome 缓存，登录态保留），`stop --all` 关掉本机所有项目的。
- 要回到旧的「每次启动、跑完关闭」，在 `browser.yaml` 的 `defaults` 里写 `resident: false`。

运行中途浏览器被关掉，会立即报「测试浏览器在运行过程中被关闭，本次结果无效」（退出码 4），不会当成流程失败去改选择器；直接重跑即可。

### 流程失败了怎么办

失败时会在 `.data-tools/browser/artifacts/` 生成诊断包，里面有失败步骤、截图和页面信息；对 AI 说「看下刚才为什么失败」即可。原来能过、突然稳定失败时，先确认被测前端是不是刚发布了新版本。

### 常见问题

- **提示「请关闭占用该 profile 的 Chrome」**：另一个 Chrome 在用同一个 profile（不是工具自己的常驻浏览器）。关掉它，或加 `--profile` 换一个目录。
- **提示「流程引用了未定义的变量」**：流程里的 `${变量}` 没有来源。在 `personal.yaml`、`.env`、`browser.yaml` 的环境里补上，或用 `--var` 传入。
- **`doctor` 提示 Playwright 未安装**：重跑 `data-tools/bootstrap.ps1` 补装依赖。
- **`doctor` 提示找不到 Chrome**：本机需要自己安装 Chrome，bootstrap 不会装它。

流程文件的完整写法见 `skills/_references/browser-flow-contract.md`。

---

## 十四、Jenkins 发版

说「发版我这个需求的模块到 dev」，AI 会对比当前分支和基线的改动，推断涉及哪些模块，回显给你确认后再触发对应的 Jenkins 任务，并回报每个构建的结果。

### 首次使用

第一次说「发版」时，AI 会依次问：

1. **Jenkins 地址**。
2. **账号**：默认拿你的 git 用户标识问你「是不是这个」，确认后写入本机 `personal.yaml`。
3. **token**：不要发在对话里。在 Jenkins 个人设置里单独生成一个可随时吊销的 API token，然后在自己的终端运行 `config.py --project <项目ID> set-secret JENKINS_TOKEN`。

token 只写进本机 `.env` 的 `JENKINS_TOKEN`，不经过对话、不写进命令行，也不会在回复里复述。共享 `jenkins.yaml` 只有地址与 `${JENKINS_USER}` 占位符；账号在本机 `personal.yaml`。

接着 AI 用 `discover` 列出 Jenkins 上的任务和参数，和你一起把「目录 → 模块 → 任务」对应起来写进 `jenkins.yaml`。这一份只留本机，通过团队内网渠道分发；每人只需运行 `project-setup` 生成自己的 `personal.yaml`，并在 `.env` 里放自己的 token。

### `jenkins.yaml` 写法

模板见 `skills/_TEMPLATE/jenkins.example.yaml`：

```yaml
jenkins:
  base_url: http://jenkins.example.com
  user: ${JENKINS_USER}
  token_key: JENKINS_TOKEN
baseline: origin/dev
build_timeout_minutes: 30
modules:
  order-service:
    paths: [order-service/]
    jobs: {dev: b2d-order-dev, test: b2d-order-test}
    params: {BRANCH: "{branch}"}
```

| 字段 | 说明 |
| --- | --- |
| `baseline` | 对比基线，改动 = 当前分支相对它的差异（不含未提交的修改） |
| `modules.*.paths` | 改动文件落在这些路径下，就认为涉及该模块，最长前缀优先 |
| `modules.*.jobs` | 环境 → Jenkins 任务名，文件夹里的任务写 `folder/job` |
| `modules.*.params` | 构建参数，`{branch}` 替换为分支名；参数名须与任务定义一致 |
| `build_timeout_minutes` | 等待单个构建完成的上限 |

模块的书写顺序就是触发顺序。

### 多个模块怎么构建

默认按顺序把所有模块的任务依次触发、放进 Jenkins 队列，之后统一等结果；这些任务实际是并行还是排队，由 Jenkins 的执行器和任务配置决定，和你在页面上逐个点击一样。前面的失败时，后面的仍会构建。

要「前一个成功才发下一个，失败就停」，对 AI 说「按顺序发，失败就停」，对应 `--sequential`。

### 同一个任务已有构建在排队或运行时

触发前会先查该任务在 Jenkins 队列里排队中的项和正在运行的构建：

- 参数和本轮相同（任务本身没有参数时，同任务的在途构建都算相同）：先取消排队项或停止正在运行的构建，再触发新的，输出 `[取消] ...，重新触发`。取消失败会报 `[取消失败]` 并照常触发，本次构建可能排在对方之后。
- 参数不同：不动对方的构建，本次构建正常入队，按 Jenkins 的规则执行。
- 自己的构建被别人取消排队项或停止时，工具会自动接管同任务、同参数的新构建继续等结果（输出 `[接管]`），最后按那个构建的结果通知你；找不到替代构建时才按取消 / ABORTED 报失败。两个人同时发同一个模块时，后发的人取消先发的人，先发的人接管后发的构建，两人都会收到同一次构建的成功结果。

`--dry-run` 会把将要取消的构建以 `[将取消]` 一并列出，确认时可以一起核对。读取排队状态失败不会阻断发版，提示后照常触发。

### 安全与权限

- 触发前一定先回显地址、分支、环境、模块和任务、参数，你说「确认」才执行。
- 触发前会检查每个模块有没有所选环境的任务、参数名是否和任务定义一致；有问题则一个都不触发。
- 账号没有某个任务的构建权限（403）时，AI 只提示你联系管理员，不会绕过。
- 触发请求失败后不会自动重试，避免重复构建；要不要重发由你决定。
- token 在对话里提供，会留在对话记录里，所以请用单独生成、可吊销的 API token。

### 常见问题

- **提示 401**：账号或 token 不对，重新提供即可。
- **提示 404**：任务名变了或不存在，让 AI 重跑 `discover` 更新映射。
- **提示某模块没有环境 xxx 的任务**：该模块的 `jobs` 里没写这个环境，补上或换环境。
- **提示任务不认识参数 / 缺少必填参数**：对照 `discover` 的输出修正 `params`。
- **「未映射文件」**：改动文件不属于任何模块（比如文档），不会触发构建；如果其实属于某个模块，补上 `paths`。
- **「未推送提交」不是 0**：Jenkins 构建的是远端代码，先推送再发版。
- **提示「未提交的改动」**：工作区里还有没提交的修改，它们不会被构建，也不计入模块推断；先提交并推送再发版。
