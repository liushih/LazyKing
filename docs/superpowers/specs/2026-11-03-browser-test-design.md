# 浏览器测试能力设计

**日期**：2026-11-03
**状态**：待审阅
**关联**：`skills/browser-test/`、`runtime/browser/`、`scripts/browser.py`、`scripts/sync_project.py`、`requirements.txt`

## 1. 背景与目标

LazyKing 已有 5 项能力（`db-access`、`data-gen-core`、`adapter-bootstrap`、`report-writer`、`git-workflow`），但浏览器上的联调、复现和回归仍靠临时脚本与人工探索。业务仓库 `hexincloud` 已有一版手工 `browser-test` 技能（Node + Markdown 手册 + `browser.mjs`），只覆盖单个项目，且每次测试仍要重新判断页面入口、选择器和等待信号。

目标是增加第 6 项能力：用可见 Chrome 执行可复跑的页面测试。第一次探索后把流程沉淀成 YAML，下次直接复跑；失败时自动生成诊断包，AI 据此修改流程，不要求人重新描述。

成功标准：

- 同事在业务仓库里说「测一下 B2D 待发货」，能直接复跑已沉淀流程，不再现场探索。
- 流程失败时，不看代码也能从诊断包判断失败步骤、期望/实际和当前页面状态。
- 首次接入新流程时，`probe` 能给出足够信息写出第一版 YAML。
- 全部使用 Python 与系统 Chrome，不要求 Node、不要求浏览器 MCP。
- 流程、坑库随业务仓库共享；凭据、截图、报告不进仓库。

## 2. 决策摘要

| 决策 | 选择 | 理由 |
|---|---|---|
| 落点 | 独立第 6 个技能 `browser-test` | 与现有 5 项能力同构，职责清晰；`skills/` 自动发现，分发零改动 |
| 技术栈 | Python Playwright，`channel="chrome"` | 符合「只支持 Python」的接入约束；使用系统 Chrome，不下载浏览器 |
| 驱动方式 | 固定 profile 的可见 Chrome，支持 `--headless` | 复用登录态，人能盯着；无人值守时可切换 |
| 记忆粒度 | 可复跑流程 + 失败自愈 | 首次探索后不再重复思考；失败可由 AI 修流程 |
| 流程格式 | YAML DSL | 与 `adapter.yaml` 写法一致，确定性高，非开发者也能改选择器 |
| 自愈方式 | 诊断包 + AI 改 YAML | 纯 Python，不依赖 MCP；不自动重试掩盖问题 |
| 造数联动 | 第一版不做，保留 `--var` 接缝 | 控制范围；以后可把批次单号传进来 |
| 首个验收 | 迁移 B2D 待发货流程 | 有现成手工流程，可直接验证迁移与复跑 |

## 3. 范围

**做**

- `runtime/browser/` 执行引擎：配置、定位、流程执行、登录、诊断、报告。
- `scripts/browser.py` 命令：`doctor`、`list`、`run`、`probe`、`diagnose`。
- 第 6 个技能 `skills/browser-test/SKILL.md` 及参考文档、模板。
- 业务仓库 `.data-tools/projects/<项目ID>/browser/` 的流程与坑库约定。
- 依赖、`.gitignore`、同步与安装、文档、测试。
- hexincloud 手工版知识迁移，并跑通 B2D 待发货。

**不做**

- 造数完成后自动触发浏览器验证。
- 自动修复选择器或自动重试。
- Playwright MCP 依赖、Node 驱动。
- 页面元素库（`pages/*.yaml`）。
- 多浏览器、移动端、视觉回归、接口 mock。
- CI 中托管浏览器测试。
- 静默下载浏览器。

## 4. 目录与边界

```text
业务仓库/
├── data-tools/
│   ├── skills/
│   │   ├── browser-test/SKILL.md            # 新技能
│   │   └── _references/
│   │       ├── browser-flow-contract.md     # DSL 契约
│   │       └── browser-diagnosis.md         # 诊断与自愈
│   ├── skills/_TEMPLATE/
│   │   ├── browser.example.yaml             # browser.yaml 模板
│   │   └── browser-flow.example.yaml        # flow 模板
│   ├── runtime/browser/
│   │   ├── __init__.py
│   │   ├── config.py                        # browser.yaml、变量、路径
│   │   ├── locator.py                       # 统一定位
│   │   ├── driver.py                        # Chrome、登录、页面原语
│   │   ├── flow.py                          # 步骤执行、等待、断言
│   │   ├── diagnose.py                      # 诊断包
│   │   └── report.py                        # 结果与产物
│   └── scripts/browser.py                   # CLI
└── .data-tools/
    ├── projects/<项目ID>/
    │   ├── .env                             # 复用现有凭据，不新增文件
    │   ├── scripts/                         # impl 代码，复用现有约定
    │   └── browser/
    │       ├── browser.yaml                 # 环境、登录、默认参数（提交）
    │       ├── flows/*.yaml                 # 可复跑流程（提交）
    │       └── pitfalls.md                  # 浏览器坑库（提交）
    └── browser/                             # 运行时目录（不提交）
        ├── profiles/<项目ID>/<env>/         # 登录态
        ├── reports/                         # 运行结果 JSON
        ├── artifacts/                       # 失败诊断包
        └── probes/                          # 探索快照
```

边界：

- `runtime/browser/` 不含任何业务知识；所有入口、选择器、登录流程都在项目 `browser/` 或项目 `scripts/` 下。
- 复用 `runtime/config.py` 已有的 `data_home()`、`project_dir()`、`resolve_project()`、`load_env()`、`substitute()`，不重复实现路径与变量解析。
- `browser.yaml` 只写 `${VAR}`，真实值留在 `.env`。
- `impl` 路径相对项目目录解析，例如 `scripts/browser_login.py:login`，与 `adapter.yaml` 的 `impl` 一致。
- 运行时产物统一落在 `.data-tools/browser/`，由 `.gitignore` 覆盖。

## 5. 配置文件 `browser.yaml`

```yaml
version: 1
project: <项目ID>

envs:
  dev:
    base_url: ${HEXIN_BASE_URL}
  test:
    base_url: ${TEST_HEXIN_BASE_URL}

defaults:
  env: dev
  timeout_ms: 15000
  headless: false
  # profile: 可选；默认 <DATA_HOME>/browser/profiles/<项目ID>/<env>

login:
  url: ${BASE_URL}/login
  username: ${HEXIN_USER}
  password: ${HEXIN_PASSWORD}
  steps:
    - click: {role: button, name: 使用账号密码登录}
      optional: true
    - fill: {placeholder: 手机号}
      value: ${username}
    - fill: {placeholder: 密码}
      value: ${password}
    - click: {role: button, name: 登 录}
  success:
    url_path: /index
    localStorage:
      Admin-Token: ".+"
```

规则：

- `project` 必须与目录名一致，不一致时报配置错误。
- `envs.<env>.base_url` 必填，指**前端页面根地址**（例如 `http://localhost`），不是接口网关；流程可通过 `${BASE_URL}` 引用。
- `login` 可省略，表示无需登录。省略时所有流程直接从 `goto` 开始。
- `login.steps` 与 `login.impl` 二选一；同时存在时报配置错误。
- `login.success` 至少提供一项（`url_path` 或 `localStorage`），用于判断登录态是否有效；`localStorage` 的值按正则搜索。配置了 `localStorage` 时以 token 为准；只有未配置 `localStorage` 时才比较 URL pathname。
- 登录流程：打开 `login.url`；若当前已满足 `success` 则跳过；否则执行 `steps`/`impl`，再校验 `success`。校验失败报环境错误。
- `defaults.headless` 可被 `--headless` 覆盖；`defaults.timeout_ms` 是单步默认超时。
- profile 路径默认 `<DATA_HOME>/browser/profiles/<项目ID>/<env>`，可被 `defaults.profile` 或 `--profile` 覆盖。

## 6. 流程 DSL

### 6.1 文件结构

```yaml
version: 1
flow: b2d-send
description: B2D 待发货列表与行内操作
env: dev
vars:
  order_no: {required: true, description: 出库单号}
steps:
  - name: 打开 B2D 出库
    goto: ${BASE_URL}/wms/outbound/outboundB2d
    wait_url: {path: /wms/outbound/outboundB2d}
```

- `flow` 必填，与文件名一致；不一致时报错。
- `env` 可省略，取 `defaults.env`；`--env` 优先级最高。
- `vars` 只声明流程参数：`required`、`default`、`description`。
- `steps` 必填且非空。

### 6.2 步骤通用字段

| 字段 | 说明 |
|---|---|
| `name` | 必填，唯一，用于报告与诊断 |
| `timeout` | 可选，覆盖默认超时（毫秒） |
| `optional` | 可选，动作目标不存在时跳过本步，不执行等待与断言 |
| 动作 | 最多一个：`goto`、`click`、`fill`、`press`、`select`、`check`、`hover`、`use_row`、`impl`；没有动作时至少包含一个 `wait_*` 或 `expect_*`（只观察/断言的步骤） |
| `as` | 可选，把本步定位结果存为别名，供后续 `in` 使用 |
| `wait_response` | 与动作并发等待的接口 |
| `wait_url` / `wait_visible` / `wait_hidden` / `wait_text` | 动作完成后依次等待 |
| `expect_*` | 动作与等待完成后断言 |

允许的顶层字段只有：`name`、`timeout`、`optional`、一个动作键、`value`、`as`、`wait_*`、`expect_*`；其余字段直接报错，避免拼写错误被静默忽略。

### 6.3 动作

| 动作 | 写法 | 说明 |
|---|---|---|
| `goto` | `goto: ${BASE_URL}/path` | 打开 URL |
| `click` | `click: {role: button, name: 搜索}` | 点击定位到的元素 |
| `fill` | `fill: {placeholder: 密码}` + `value: ...` | 填写输入框 |
| `press` | `press: Enter` | 当前焦点按键 |
| `select` | `select: {label: 状态}` + `value: ...` | 下拉选择 |
| `check` | `check: {testid: agree}` | 勾选复选框 |
| `hover` | `hover: {text: 更多}` | 悬停 |
| `use_row` | `use_row: {text: "${order_no}", checkbox: "input.standard-checkbox"}` | 在 `row_css`（默认 `table tbody tr`）中按文本定位行，存入别名；可断言 `wait_visible: true` |
| `impl` | `impl: scripts/xxx.py:func` | 调用项目内 Python 函数 |

`impl` 约定：

- 函数签名 `func(ctx) -> dict | None`。
- `ctx` 提供 `page`、`browser`、`vars`、`project_dir`、`data_home`、`logger`、`step`。
- 返回 dict 合并进 `ctx.vars`；后续步骤可直接引用 `${key}`。
- 抛异常即本步失败，诊断包照常生成。

### 6.4 定位器

统一定位写法，可用于所有动作、等待与断言：

| 写法 | 解析 |
|---|---|
| `{testid: b2d-update-logistics-dialog}` | `[data-testid="..."]` |
| `{role: button, name: 搜索, exact: true}` | `get_by_role` |
| `{text: 修改物流方式, exact: true}` | `get_by_text` |
| `{placeholder: 手机号}` | `get_by_placeholder` |
| `{css: "table tbody tr"}` | CSS |
| `{in: row, role: button, name: 更多}` | 在上一步 `as: row` 保存的定位器内查找 |
| `{..., last: true}` | 取最后一个匹配；默认严格匹配，多个命中报错 |

定位到多个元素且未加 `last: true` 时按失败处理，并在诊断包记录命中数量与候选文本。

### 6.5 等待

| 写法 | 语义 |
|---|---|
| `wait_response: /wms/pickingPlan/list` | 与动作并发等待 URL 包含该串的响应，默认 2xx |
| `wait_response: {url_contains: ..., status: 200}` | 指定状态码 |
| `wait_url: {path: /index}` | 等待 pathname 精确等于 |
| `wait_url: {contains: /wms/outbound}` | 等待 URL 包含 |
| `wait_visible: {testid: ...}` | 等待可见 |
| `wait_hidden: {css: ...}` | 等待消失 |
| `wait_text: {locator: {...}, contains: 保存成功}` | 等待文本出现 |

不提供 `sleep` 或 `waitForTimeout`；需要固定停顿时说明信号没找对，应先补等待条件。

### 6.6 断言

| 写法 | 语义 |
|---|---|
| `expect_visible: {testid: ...}` | 必须可见 |
| `expect_hidden: {css: ...}` | 必须不可见 |
| `expect_text: {locator: {...}, contains: 物流方式已修改}` | 文本包含 |
| `expect_text: {locator: {...}, equals: ...}` | 文本完全相等 |
| `expect_url: {path: /wms/outbound/outboundB2d}` | pathname 相等 |
| `expect_count: {locator: {...}, min: 1}` | 元素数量范围，支持 `eq` / `min` / `max`；统计全部命中 |

断言失败即流程失败，诊断包记录期望值与实际值。

### 6.7 示例

```yaml
version: 1
flow: b2d-send
description: B2D 待发货列表、修改物流方式与操作日志
env: dev
vars:
  order_no: {required: true, description: 出库单号}

steps:
  - name: 打开 B2D 出库
    goto: ${BASE_URL}/wms/outbound/outboundB2d
    wait_url: {path: /wms/outbound/outboundB2d}

  - name: 切到待发货
    click: {role: tab, name: 待发货}
    wait_response: /wms/pickingPlan/list
    wait_visible: {css: "table tbody tr"}

  - name: 定位目标行
    use_row: {text: "${order_no}", checkbox: "input.standard-checkbox"}
    as: row
    wait_visible: true

  - name: 打开更多菜单
    click: {in: row, role: button, name: 更多}
    wait_visible: {text: 修改物流方式, exact: true}

  - name: 打开修改物流方式
    click: {text: 修改物流方式, exact: true, last: true}
    wait_response: /b2dLogistics/context
    wait_visible: {testid: b2d-update-logistics-dialog}
    expect_text: {locator: {testid: b2d-update-logistics-dialog}, contains: 物流方式}

  - name: 打开行日志
    click: {in: row, role: button, name: 日志}
    wait_response: /log/operlog/treeByBizKey
    wait_visible: {css: ".el-drawer:visible"}
    expect_visible: {css: ".el-drawer:visible"}
```

## 7. 变量与解析顺序

`${NAME}` 依次从以下来源解析，先命中者生效：

1. 流程变量：`--var` 传入值 > 流程 `vars.<name>.default`。
2. 当前环境配置：`envs.<env>.*`，`base_url` 以 `BASE_URL` 暴露。
3. 进程环境变量。

解析后仍缺失：必填变量报配置错误；非必填保留空串并告警。

`browser.yaml` 中的 `${VAR}` 也在同一机制下解析，凭据因此只存 `.env`。

## 8. 执行与登录

1. 解析项目：`--project`，未给时读 `.data-tools/config.yaml` 的 `default_project`；仍无则报错。
2. 加载 `browser/browser.yaml` 与 `flows/<flow>.yaml`；做结构和未知字段校验。
3. 解析 env 与变量；检查必填参数。
4. 启动 Chrome：`channel="chrome"`、`headless` 取配置或 `--headless`、`viewport=None`、`acceptDownloads=True`、固定 profile。
5. 复��登录态：打开 `login.url`，满足 `success` 即跳过登录；否则执行登录步骤后再次校验。
6. 逐步执行。`wait_response` 与动作并发，其余等待按声明顺序执行，最后断言。
7. 关闭上下文（`--trace` 时先保存 `trace.zip`）。

profile 被占用、Chrome 不存在、Playwright 未安装等环境问题在启动阶段直接失败，不进入步骤执行。

## 9. CLI

```text
python scripts/browser.py doctor   --project <项目ID>
python scripts/browser.py list     --project <项目ID> [--json]
python scripts/browser.py run      --project <项目ID> --flow <名称> [--env dev] [--var K=V ...] [--headless] [--trace] [--json]
python scripts/browser.py probe    --project <项目ID> --url <URL> [--label <名称>]
python scripts/browser.py diagnose --project <项目ID> [--last]
```

### 9.1 `doctor`

检查并打印：Python 版本、Playwright 版本与能否导入、系统 Chrome 路径、profile 目录可写、`browser.yaml` 是否存在、流程数量、`browser.yaml` 引用的变量在 `.env` 中是否齐全（只报键名）。任一项失败给出可执行的修复提示。退出码：`0` 全部通过，`2` 配置缺失或非法，`4` 环境不可用。

### 9.2 `list`

列出流程名、描述、默认 env、必填变量。`--json` 输出结构化列表。

### 9.3 `run`

- 参数：`--flow` 必填；`--var` 可重复；`--env`、`--headless`、`--profile` 覆盖配置；`--trace` 保存轨迹；`--json` 输出机器可读结果。
- 成功输出：流程名、步骤数、总耗时、报告路径。
- 失败输出：失败步骤、期望/实际、诊断包路径。
- 不打印任何凭据或 `.env` 值。
- 报告写入 `.data-tools/browser/reports/<flow>-<时间戳>.json`。
- 运行前清理旧产物，仅保留最近 20 份报告与 20 份诊断包。

### 9.4 `probe`

用于首次探索。打开指定 URL（必要时登录），等待页面稳定后采集：

- `probe.md`：页面标题、URL、可交互元素摘要、表格行样貌、最近接口、可能的选择器建议。
- `page.png`：整页截图。
- `page.html`：当前 DOM。
- `elements.json`：按角色/文本/testid/CSS 汇总的可交互元素。
- `requests.json`：最近 50 个请求（脱敏）。
- `console.log`：前端报错与告警。

采集前等待 `load` 事件，再最多等 2 秒网络空闲（超时也继续采集，不阻塞）。输出到 `.data-tools/browser/probes/<时间戳>-<label>/`，时间戳格式为 `YYYYMMDD-HHMMSS-毫秒`。AI 据此写第一版流程 YAML。

### 9.5 `diagnose`

打印最近一次诊断包的 `diagnosis.md` 与产物路径，便于重看；没有诊断包时退出码 `2`。

### 9.6 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 流程执行失败或断言失败 |
| 2 | 配置错误（文件缺失、字段非法、必填变量缺失） |
| 3 | 流程不存在 |
| 4 | 环境错误（Python/Playwright/Chrome/profile/登录失败） |

## 10. 报告与诊断包

### 10.1 报告 JSON

```json
{
  "flow": "b2d-send",
  "env": "dev",
  "result": "pass",
  "started_at": "2026-11-03T10:00:00+08:00",
  "duration_ms": 8421,
  "flow_file": ".data-tools/projects/hexincloud/browser/flows/b2d-send.yaml",
  "artifacts": null,
  "steps": [
    {"name": "打开 B2D 出库", "status": "pass", "duration_ms": 1200},
    {"name": "定位目标行", "status": "pass", "duration_ms": 300}
  ]
}
```

- `status` 取值：`pass`、`fail`、`skipped`。
- 失败步骤带 `error`，包含异常类型、消息和定位命中信息。
- `skipped` 仅用于 `optional: true`。

### 10.2 诊断包

`.data-tools/browser/artifacts/<flow>-<时间戳>/`，时间戳格式为 `YYYYMMDD-HHMMSS-毫秒`：

| 文件 | 内容 |
|---|---|
| `diagnosis.md` | 失败步骤、期望/实际、当前 URL、页面线索、接口线索、建议动作 |
| `failure.png` | 失败瞬间截图 |
| `page.html` | 当前 DOM |
| `requests.json` | 最近 50 个请求，去掉 Cookie/Authorization/Set-Cookie |
| `console.log` | 前端报错与告警 |
| `flow.snapshot.yaml` | 本次执行的流程副本 |
| `run.log` | 运行日志 |
| `trace.zip` | 仅 `--trace` 时生成 |

`diagnosis.md` 至少包含：

- 失败步骤名与序号。
- 期望信号与实际状态（例如「等待 `/xxx` 返回，实际 30 秒内未出现」）。
- 定位失败时的命中数量与候选元素文本。
- 当前 URL 与页面标题。
- 建议：优先检查选择器、接口路径、页面是否跳转、是否需要额外等待信号。

## 11. 自愈与记忆

### 11.1 自愈循环（写入技能）

```text
run 失败
→ 读 diagnosis.md 与产物
→ 判断属于哪类：选择器变化 / 等待信号不对 / 接口路径变化 / 前置条件缺失
→ 修改 flow YAML；复杂交互抽到 impl
→ 重跑，直到退出码 0
→ 出现新坑按四段式追加 browser/pitfalls.md
→ 只以退出码 0 报通过；未通过时明确说失败步骤
```

### 11.2 坑库格式

`browser/pitfalls.md` 沿用项目现有四段式：

```markdown
## P1 侧边栏也有「查询」按钮

- 现象：点击查询后列表没刷新，实际点到了侧边栏
- 原因：文本选择器同时命中侧边栏和页面按钮
- 绕法：用 `{testid: ...}` 或 `{in: row, ...}` 限定范围
- 适用：所有带同名侧边栏按钮的页面
```

追加前按「现象」去重；同一现象更新绕法，不新增重复条目。

### 11.3 记忆边界

- 提交：`browser.yaml`、`flows/*.yaml`、`pitfalls.md`、项目 `scripts/` 下的 impl。
- 不提交：`.data-tools/browser/` 全部内容。
- `browser.yaml` 不出现真实凭据；新增凭据键时同步更新 `.env.example`。

## 12. 技能 `browser-test`

**触发**：测一下、走一遍、浏览器验证、点一遍、复现一下、回归、页面确认。

**第 0 步**：与现有 5 个技能相同的环境检查（定位 `<TOOLS_DIR>` / `<DATA_HOME>`、Python 3.11+、venv、版本检查）。

**执行顺序**：

1. 定位项目与 `browser/browser.yaml`。
2. `list` 查看已沉淀流程；命中就直接 `run`，不重新探索。
3. 没有对应流程时：
   - `probe --url` 获取页面快照；
   - 按 `_references/browser-flow-contract.md` 写 `flows/<名称>.yaml`；
   - `run` 并修正，直到通过；
   - 把入口、等待信号、坑写入流程与 `pitfalls.md`。
4. 失败按第 11 节自愈。
5. 报告结果时给出：流程名、通过/失败步骤、耗时、产物路径。

**不适用**：只查库 → `db-access`；批量造数 → `data-gen-core`；定位后端根因 → 其它排障技能。

**铁律**：

- 先查流程与坑库，不重复探索。
- 不写固定 sleep。
- 选择器必须唯一，优先 `data-testid`，其次角色/精确文本。
- 一条流程一次连接，不在步骤间重开浏览器。
- 业务逻辑只进项目 `scripts/`，不进 `runtime/`。

## 13. 分发与迁移

### 13.1 分发

- `skills/browser-test/SKILL.md` 会被 `install.py` 与 `sync_project.py` 自动发现，无需新增名单。
- `requirements.txt` 增加 Playwright（实现时固定当前稳定版本）。Playwright Python 自带驱动，不要求同事安装 Node。
- `bootstrap.ps1` 走现有依赖安装；不执行 `playwright install`，不下载 Chromium。
- `sync_project.py` 的 `.gitignore` 块增加：

```gitignore
.data-tools/browser/
```

- `README.md`、`docs/usage.md` 增加第 6 个技能与浏览器测试说明。
- `skills/_references/project-layout.md` 增加 `browser/` 目录说明。

### 13.2 hexincloud 手工版迁移

1. 先把现有知识迁到 `.data-tools/projects/hexincloud/browser/`：
   - `00-环境与登录.md` → `browser.yaml`（地址、登录、成功标志）。
   - `02-通用手法.md`、`01-浏览器接入与排障.md` → `pitfalls.md` 与流程等待信号。
   - `flows/B2D待发货.md` → `flows/b2d-send.yaml`。
2. 用 Python 复跑 B2D 流程，确认登录复用、改物流方式、日志三个动作通过。
3. 通过后删除旧 `.claude/skills/browser-test` 与 Node 脚本；`.mcp.json` 的 Playwright MCP 保留给人临时看页面，不作为能力依赖。
4. 再执行 `sync_project.py`，生成新技能入口，避免旧目录被直接覆盖导致知识丢失。

## 14. 文件级改动

| 文件 | 改动 |
|---|---|
| `runtime/browser/__init__.py` | 新增：包入口 |
| `runtime/browser/config.py` | 新增：项目/环境/变量/profile 解析、YAML 校验；复用 `runtime/config.py` |
| `runtime/browser/locator.py` | 新增：定位器解析与查找 |
| `runtime/browser/driver.py` | 新增：Chrome 启动、登录、页面原语 |
| `runtime/browser/flow.py` | 新增：步骤执行、等待、断言、impl 调用 |
| `runtime/browser/diagnose.py` | 新增：截图、DOM、请求、console、diagnosis.md |
| `runtime/browser/report.py` | 新增：报告写入、产物清理与脱敏 |
| `scripts/browser.py` | 新增：`doctor` / `list` / `run` / `probe` / `diagnose` |
| `skills/browser-test/SKILL.md` | 新增：第 6 个技能 |
| `skills/_references/browser-flow-contract.md` | 新增：DSL 完整契约 |
| `skills/_references/browser-diagnosis.md` | 新增：诊断包与自愈指南 |
| `skills/_TEMPLATE/browser.example.yaml` | 新增：`browser.yaml` 模板 |
| `skills/_TEMPLATE/browser-flow.example.yaml` | 新增：流程模板 |
| `requirements.txt` | 增加 Playwright |
| `scripts/sync_project.py` | `.gitignore` 块增加 `.data-tools/browser/` |
| `skills/_references/project-layout.md` | 增加 `browser/` 目录与产物边界 |
| `README.md`、`docs/usage.md` | 增加浏览器测试能力说明 |
| `tests/test_browser_config.py` | 新增 |
| `tests/test_browser_locator.py` | 新增 |
| `tests/test_browser_driver.py` | 新增：Chrome 启动、profile 占用、登录态检测 |
| `tests/test_browser_flow.py` | 新增：本地 HTML fixture 覆盖流程执行 |
| `tests/test_browser_report.py` | 新增 |
| `tests/test_browser_cli.py` | 新增 |
| `tests/test_skills.py` | 修改：断言 6 个技能且新技能含第 0 步 |
| `tests/test_sync_project.py` | 修改：断言 `.gitignore` 含 `.data-tools/browser/` |

不改现有 5 项能力的执行逻辑；不改造数、查库、报告、Git 托管。

## 15. 测试与验收

**自动化**

- 配置：`browser.yaml` 结构校验、项目名不一致、env 缺失、变量解析顺序、必填变量缺失。
- DSL：未知字段、多动作、步骤名重复、`flow` 与文件名不一致、`optional` 语义。
- 定位器：各写法解析；多命中且未加 `last` 时报错。
- 报告：JSON 结构、失败步骤字段、产物清理只保留最近 20 份。
- 诊断：请求头脱敏、`.env` 值不落盘、`diagnosis.md` 必含字段。
- CLI：`list` / `run` / `probe` / `doctor` 的退出码；`--json` 输出。
- 浏览器集成：用本地静态 HTML fixture 覆盖 `goto`、`click`、`fill`、`wait_visible`、`expect_text`、`use_row`、`impl`；没有系统 Chrome 时跳过并说明。
- 分发：临时业务仓库 sync 后出现第 6 个技能、模板、参考文档与忽略块。

**手工验收**

1. `doctor` 在装有 Chrome 的机器上全部通过；卸载 Playwright 时给出明确提示。
2. 在 hexincloud 用真实单号跑 `b2d-send` 通过。
3. 第二次运行直接复用登录态，不出现登录步骤。
4. 故意改错一个选择器：失败退出码 1，诊断包含截图、DOM、接口、失败步骤。
5. 按诊断包改回选择器后重跑通过；新坑追加到 `pitfalls.md`。
6. `--headless` 可跑通。
7. `--var order_no=<另一单号>` 能定位到另一行。
8. `--trace` 生成 `trace.zip` 且可打开。
9. 仓库 `git status` 不出现产物、凭据、profile。
10. 新同事仓库按 README 操作后，能说「测一下 B2D 待发货」并跑通。

## 16. 风险与取舍

| 风险 | 影响 | 应对 |
|---|---|---|
| Playwright 与系统 Chrome 版本不匹配 | 启动失败 | `doctor` 输出两者版本与修复建议；不自动下载浏览器 |
| profile 被另一个 Chrome 占用 | 启动失败 | 报错给出关闭占用或 `--profile` 覆盖 |
| 选择器漂移导致 flaky | 测试不可信 | 诊断包 + 坑库闭环；默认严格匹配；不自动重试掩盖 |
| 同事机器没装 Chrome | 无法运行 | `doctor` 提示安装 Chrome，能力不静默降级 |
| 诊断包含敏感信息 | 泄露风险 | 请求头脱敏、不写 `.env` 值、产物目录不进仓库 |
| 旧 browser-test 技能被同名生成物覆盖 | 知识丢失 | 先迁移到项目 `browser/` 再 sync |
| 流程 YAML 越写越复杂 | 难维护 | 复杂交互抽到 `impl`；DSL 只保留页面原语 |
| 无头模式行为差异 | 仅可见模式通过 | 验收包含 `--headless`；失败诊断同样落盘 |

## 17. 实施顺序

1. **引擎**：`runtime/browser/` 的配置、定位、驱动、流程、报告、诊断；配单元测试。
2. **CLI**：`scripts/browser.py` 五个子命令；配 CLI 测试。
3. **技能与文档**：`SKILL.md`、DSL 契约、诊断指南、模板；更新 README、usage、project-layout。
4. **分发**：`requirements.txt`、`sync_project.py` 忽略块、`test_skills.py`、`test_sync_project.py`。
5. **试点迁移**：hexincloud 知识迁移、B2D 流程跑通、自愈演练、无头验收。
6. **端到端**：临时业务仓库 sync 后走一遍同事接入流程。

每步完成跑 `pytest`；第 5 步完成后按第 15 节手工验收全部过一遍。

## 18. 后续（不在本期）

- 造数批次完成后自动传入单号做浏览器验证。
- 页面元素库 `pages/*.yaml`，减少跨流程选择器重复。
- 视觉回归与截图基线。
- 多浏览器（Edge/Firefox）与移动端。
- 失败自动建议补丁（仍由人确认后写入）。
- CI 中运行无头回归。
