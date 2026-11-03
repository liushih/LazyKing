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
  headless: false
  # profile: 可选；默认 <DATA_HOME>/browser/profiles/<项目ID>/<env>

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
| `wait_response: /api/list` | 与动作并发等待 URL 包含该串、状态 2xx |
| `wait_response: {url_contains: /api/list, status: 200}` | 指定状态码 |
| `wait_url: {path: /index}` | pathname 精确相等 |
| `wait_url: {contains: /wms/outbound}` | URL 包含 |
| `wait_visible: {testid: ...}` | 等待可见 |
| `wait_hidden: {css: ...}` | 等待消失 |
| `wait_text: {locator: {css: ...}, contains: 保存成功}` | 等待文本 |

不提供固定 sleep。需要停顿时说明等待信号没找对。

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

`success.url_path` 只比较 pathname，不匹配 query，避免登录页 `redirect=/index` 误判。

## 10. 命令与退出码

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" doctor --project <项目ID>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" list --project <项目ID>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" run --project <项目ID> --flow <名称> --env dev --var order_no=WO001
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" probe --project <项目ID> --url ${BASE_URL}/index
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/browser.py" diagnose --project <项目ID>
```

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 流程失败 |
| 2 | 配置错误 |
| 3 | 流程不存在 |
| 4 | 环境错误 |
