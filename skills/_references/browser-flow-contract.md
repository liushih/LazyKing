# 浏览器流程契约

`browser-test` 读取两个文件：项目级 `browser/browser.yaml` 和流程级 `browser/flows/<名称>.yaml`。本文件是两者的完整写法。

## 1. browser.yaml

```yaml
version: 1
project: <项目ID>

envs:
  dev:
    base_url: ${WEB_BASE_URL}
  test:
    base_url: ${TEST_WEB_BASE_URL}

defaults:
  env: dev
  timeout_ms: 15000
  headless: false   # 仅 resident: false 时生效；常驻浏览器固定无头
  # resident: 可选；默认 true，后台常驻无头 Chrome 不弹窗；false 回到每次启动、跑完关闭
  # profile: 可选；默认 <DATA_HOME>/browser/profiles/<项目ID>/<env>
  # api_watch: 可选；接口异常快速失败，见第 5.1 节

login:
  url: ${BASE_URL}/login
  username: ${WEB_USERNAME}
  password: ${WEB_PASSWORD}
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

- `project` 必须与目录名一致。
- `envs.<env>.base_url` 指**前端页面根地址**，不是接口网关。
- 所有值先与系统环境变量、项目 `.env` 合并（`.env` 覆盖同名系统变量），再替换 `${VAR}`。
- `login` 可省略，表示无需登录。
- `login.steps` 与 `login.impl` 二选一；`login.success` 至少提供 `url_path` 或 `localStorage`。
- 配置了 `localStorage` 时以 token 为准；只有未配置 `localStorage` 时才比较 `url_path` 的 pathname。
- `login.url` 可以写 `${BASE_URL}/login`，运行时按环境解析。
- `login.steps` 里的 `${username}`、`${password}` 来自 `login.username` / `login.password`。
- `defaults.profile` 可写固定路径；否则按项目 + 环境隔离。

## 2. 流程文件

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
    expect_visible: {css: ".el-drawer:visible"}
```

- `flow` 必须与文件名一致。
- `env` 可省略，取 `defaults.env`。
- `vars` 声明参数：`required`、`default`、`description`。
- 每个步骤必须有唯一 `name`，最多一个动作。
- **只断言、不操作的步骤是允许的**：零个动作 + 至少一个 `wait_*` 或 `expect_*`。
- `wait_response` 必须配合动作使用。
- 可选步骤字段：`timeout`（毫秒，覆盖默认超时）、`optional`、`as`、`allow_api_error`（见 5.1）。

## 3. 动作

| 动作 | 写法 | 说明 |
|---|---|---|
| `goto` | `goto: ${BASE_URL}/path` | 打开 URL |
| `click` | `click: {role: button, name: 搜索}` | 点击 |
| `fill` | `fill: {placeholder: 密码}` + `value: ...` | 填输入框 |
| `press` | `press: Enter` | 当前焦点按键 |
| `select` | `select: {label: 状态}` + `value: ...` | 下拉选择 |
| `check` | `check: {testid: agree}` | 勾选 |
| `hover` | `hover: {text: 更多}` | 悬停 |
| `use_row` | `use_row: {text: "${order_no}", checkbox: "input.standard-checkbox"}` | 按文本定位表格行 |
| `impl` | `impl: scripts/xxx.py:func` | 调用项目内 Python |

`use_row` 可选 `row_css`（默认 `table tbody tr`）和 `checkbox`；`as` 把定位结果存为别名，后续用 `{in: 别名, ...}` 限定范围。

## 4. 定位器

| 写法 | 解析 |
|---|---|
| `{testid: b2d-update-logistics-dialog}` | `[data-testid="..."]` |
| `{role: button, name: 搜索, exact: true}` | `get_by_role` |
| `{text: 修改物流方式, exact: true}` | `get_by_text` |
| `{placeholder: 手机号}` | `get_by_placeholder` |
| `{css: "table tbody tr"}` | CSS |
| `{in: row, role: button, name: 更多}` | 在别名范围内查找 |
| `{..., last: true}` | 取最后一个 |

默认严格匹配：多个命中直接失败，并在诊断包记录命中数量与候选文本。`expect_count` 例外，它统计全部命中。

## 5. 等待

| 写法 | 语义 |
|---|---|
| `wait_response: /api/list` | 与动作并发等待 URL 包含该串；响应一到即判定，状态非 2xx 或业务码异常立刻失败（接口监听关闭时仍等 2xx） |
| `wait_response: {url_contains: /api/list, status: 200}` | 指定状态码；写了 `status` 就只按该状态匹配，不做业务码检查 |
| `wait_url: {path: /index}` | pathname 精确相等 |
| `wait_url: {contains: /wms/outbound}` | URL 包含 |
| `wait_visible: {testid: ...}` | 等待可见 |
| `wait_hidden: {css: ...}` | 等待消失 |
| `wait_text: {locator: {css: ...}, contains: 保存成功}` | 等待文本 |

不提供固定 sleep。需要停顿时说明等待信号没找对。所有等待都是条件一满足立即继续，`timeout_ms` 只是失败时的上限。

### 5.1 接口异常快速失败

步骤的等待/断言期间，页面发出的接口请求出错时，不必等到超时才报错。判定标准（通用约定）：

| 类别 | 判为异常 |
|---|---|
| HTTP | `xhr` / `fetch` 与主页面请求状态码 ≥ 400；图片、脚本等静态资源 404 不算 |
| 业务 | HTTP 200 但 JSON 响应体顶层 `success: false`，或 `code` 不在成功码内（默认 `0`、`200`、`"ok"`、`"success"`，忽略大小写） |
| 网络 | 请求失败（`ERR_ABORTED` 即页面跳转或前端主动取消的除外） |

- **宽限期**：接口报错后，若等待条件在 `grace_ms`（默认 1500）内仍未满足才判失败；页面自己重试成功的不会误判。
- 失败信息含 URL、状态/业务码、响应片段，写入报告和诊断包的 `diagnosis.md`「接口异常」一节。
- 只看当前步骤期间出现的接口；步骤没有任何等待/断言时不会中途判失败。

`browser.yaml` 可调：

```yaml
defaults:
  api_watch:
    enabled: true            # 默认开启
    ignore: [/api/heartbeat] # URL 子串；这些接口出错一律不算
    success_codes: [0, 200]  # 覆盖默认成功码
    grace_ms: 1500
```

步骤上可局部放行（例如专门验证报错提示的反向用例）：

```yaml
- name: 提交空表单
  click: {testid: submit}
  allow_api_error: true            # 整步不监听
  # allow_api_error: [/api/save]   # 或只放行这些 URL
  expect_text: {locator: {css: .el-message}, contains: 不能为空}
```

## 6. 断言

| 写法 | 语义 |
|---|---|
| `expect_visible: {testid: ...}` | 必须可见 |
| `expect_hidden: {css: ...}` | 必须不可见 |
| `expect_text: {locator: {css: ...}, contains: 物流方式已修改}` | 文本包含 |
| `expect_text: {locator: {css: ...}, equals: 成功}` | 文本完全相等 |
| `expect_url: {path: /wms/outbound/outboundB2d}` | pathname 相等 |
| `expect_count: {locator: {css: "table tbody tr"}, eq: 2}` | 数量，支持 `eq` / `min` / `max` |

## 7. 变量

`${NAME}` 按以下顺序解析，先命中者生效：

1. `--var` 传入值
2. 流程 `vars.<name>.default`
3. 当前环境配置（`envs.<env>.*`，`BASE_URL` 为前端根地址）
4. 系统环境变量

必填变量缺失会在启动浏览器前报配置错误。非必填且无默认值的变量为空串。

## 8. impl

```yaml
- name: 复杂步骤
  impl: scripts/browser_step.py:run
```

- 函数签名 `func(ctx) -> dict | None`。
- `ctx` 提供 `page`、`vars`、`project_dir`、`data_home`、`logger`、`step`。
- 返回 dict 合并进后续变量。
- 抛异常即本步失败，诊断包照常生成。
- `impl` 路径相对项目目录解析。

## 9. 登录

登录流程：

1. 打开 `login.url`。
2. 已满足 `success` 则跳过。
3. 否则执行 `login.steps` 或 `login.impl`。
4. 再校验 `success`；不通过报环境错误。

`success.url_path` 只在未配置 `localStorage` 时使用；配置了 token 时以 token 为准，避免页面停在登录页但实际已登录的误判。

## 10. 命令与退出码

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" doctor --project <项目ID>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" list --project <项目ID>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" run --project <项目ID> --flow <名称> --env dev --var order_no=WO001
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" probe --project <项目ID> --url ${BASE_URL}/index
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" diagnose --project <项目ID>
```

### 选项

| 选项 | 适用 | 说明 |
|---|---|---|
| `--var 名称=值` | run | 流程参数，可重复；必填变量缺失在启动浏览器前报错 |
| `--env 名称` | run / probe | 指定环境；默认取流程的 `env`，再取 `defaults.env` |
| `--headless` | run / probe | 一次性启动（`resident: false`）时不显示窗口；常驻模式本来就是无头，此项无影响 |
| `--headed` | run / probe | 本次显示窗口（最大化）；一次性启动，会先关掉该 profile 的常驻浏览器 |
| `--profile 路径` | run / probe | 换浏览器 profile，用于绕开被占用的 profile 或强制重新登录 |
| `--trace` | run | 录制 Playwright trace；只在失败时随诊断包保留，通过后自动删除 |
| `--json` | list / run | 机器可读输出 |
| `--label 名称` | probe | 探索快照名称 |
| `--all` | stop / clean | stop：关闭本机所有项目的常驻浏览器；clean：清空运行产物并清理本机所有 profile 缓存 |

### 常驻浏览器

默认（`defaults.resident: true`）：`run` / `probe` 连接一个后台常驻的专用无头 Chrome，跑完只关自己开的页面并断开，浏览器留着给下一次用。

- 状态文件：`<profile>.resident.json`（pid、调试端口），与 profile 目录同级；调试端口只监听 `127.0.0.1`，每次随机。
- 不存在或已被关闭时，下一次 `run` 自动拉起；`stop` 关闭它。
- 同一 profile 同时只能被一个 Chrome 占用：`--headed` 和 `resident: false` 的一次性启动会先关掉该 profile 的常驻浏览器。
- 运行中浏览器被关：退出码 4，提示「测试浏览器在运行过程中被关闭」，不生成诊断包。

视口：常驻和 `--headless` 固定 1280x720，`--headed` 最大化。两者页面尺寸不同，对比失败时要用同一种模式。

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 流程失败 |
| 2 | 配置错误（含流程引用了未定义的变量） |
| 3 | 流程不存在 |
| 4 | 环境错误（含运行中测试浏览器被关闭） |
