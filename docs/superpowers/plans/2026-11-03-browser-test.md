# 浏览器测试能力实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 data-tools 增加第 6 个能力：用 Python Playwright 驱动系统 Chrome，按 YAML 流程复跑页面测试，失败时生成诊断包供 AI 自愈。

**Architecture:** 新增 `runtime/browser/` 执行引擎（配置、定位、驱动、流程、报告、诊断）、`scripts/browser.py` 命令入口和 `skills/browser-test/` 技能。业务知识全部放在 `.data-tools/projects/<项目ID>/browser/`，运行时产物放在不提交的 `.data-tools/browser/`。

**Tech Stack:** Python 3.11+、Playwright Python（sync API）、系统 Chrome（`channel="chrome"`）、PyYAML、pytest。

**Spec:** `docs/superpowers/specs/2026-11-03-browser-test-design.md`

## Global Constraints

- 只支持 Python 3.11+；不引入 Node 依赖，不执行 `playwright install`，只用系统 Chrome。
- 浏览器默认可见，固定 profile；`--headless` 覆盖。
- 流程中禁止固定 sleep；内部轮询间隔 50ms。
- 选择器默认严格匹配，多命中即失败并记录候选。
- 凭据只放项目 `.env`；YAML 中只写 `${VAR}`。
- 运行时产物只写 `.data-tools/browser/`，不提交。
- 报告与诊断包只保留最近 20 份。
- CLI 退出码：`0` 通过、`1` 流程失败、`2` 配置错误、`3` 流程不存在、`4` 环境错误。
- 新技能的 `SKILL.md` 必须包含「第 0 步：环境检查」，命令块不留反斜杠续行。
- 现有 5 项能力的执行逻辑不改。

## Review Focus

1. **定位器多命中**：同一文本命中侧边栏和页面按钮时，必须立即失败并给出命中数量与候选文本，而不是点错元素。
2. **profile 被占用**：同一 profile 第二次启动 Chrome 时，报错要包含 profile 路径与「关闭占用窗口」，不能只抛 Playwright 原始堆栈。
3. **登录成功误判**：登录页 URL 的 `redirect` 参数含成功路径时，不能判为已登录；只比较 pathname。
4. **变量缺失**：必填变量或 `${VAR}` 未定义时，在启动浏览器前报配置错误并列出键名。
5. **诊断采集失败**：页面已崩溃或截图失败时，仍要写出 `diagnosis.md` 并保留原始流程错误。

---

### Task 1: 依赖与配置解析

**Files:**
- Modify: `requirements.txt`
- Create: `runtime/browser/__init__.py`
- Create: `runtime/browser/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_browser_config.py`

**Interfaces:**
- Consumes: `runtime.config.data_home()`, `project_dir()`, `load_env()`, `substitute()`。
- Produces:
  - `BrowserConfigError(Exception)`
  - `FlowNotFoundError(BrowserConfigError)`
  - `EnvConfig(name: str, base_url: str, values: dict[str, str])`
  - `LoginConfig(url: str, username: str | None, password: str | None, steps: list[dict], impl: str | None, success_url_path: str | None, success_localstorage: dict[str, str])`
  - `VarDef(required: bool, default: str | None, description: str)`
  - `FlowDef(name: str, description: str, env: str | None, vars: dict[str, VarDef], steps: list[dict], path: Path)`
  - `BrowserConfig(project: str, envs: dict[str, EnvConfig], default_env: str, timeout_ms: int, headless: bool, profile: Path | None, login: LoginConfig | None)`
  - `load_browser_config(project_id: str) -> BrowserConfig`
  - `load_flow(project_id: str, flow_name: str) -> FlowDef`
  - `list_flows(project_id: str) -> list[FlowDef]`
  - `resolve_variables(cfg: BrowserConfig, flow: FlowDef, env_name: str, cli_vars: dict[str, str], os_env: dict[str, str] | None = None) -> dict[str, str]`
  - `profile_path(cfg: BrowserConfig, env_name: str, override: Path | None = None) -> Path`

- [ ] **Step 1: 固定 Playwright 版本并安装**

Run: `.venv/Scripts/python.exe -m pip index versions playwright`
Expected: 输出当前可安装的最新版本号。

把 `requirements.txt` 末尾追加一行：`playwright==` 拼接上一步输出的最新稳定版本号。

Run: `.venv/Scripts/python.exe -m pip install -r requirements.txt`
Expected: 安装成功；`.venv/Scripts/python.exe -c "import playwright; print(playwright.__version__)"` 输出版本号。

- [ ] **Step 2: 写共享测试夹具**

Create `tests/conftest.py`:

```python
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "browser_fixture"
DEFAULT_BROWSER_YAML = """
version: 1
project: demo
envs:
  dev:
    base_url: ${WEB}
    api: ${API}
defaults:
  env: dev
  timeout_ms: 12000
  headless: false
login:
  url: ${WEB}/login
  username: ${USER}
  password: ${PASS}
  steps:
    - fill: {placeholder: 手机号}
      value: ${username}
  success:
    url_path: /index
    localStorage:
      Admin-Token: ".+"
"""
DEFAULT_FLOW_YAML = """
version: 1
flow: smoke
description: 冒烟
env: dev
vars:
  order_no: {required: true, description: 单号}
steps:
  - name: 打开首页
    goto: ${BASE_URL}/index
"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def fixture_url():
    handler = functools.partial(_QuietHandler, directory=str(FIXTURE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser_context(tmp_path_factory):
    sync_api = pytest.importorskip("playwright.sync_api")
    profile = tmp_path_factory.mktemp("chrome-profile")
    playwright = sync_api.sync_playwright().start()
    try:
        context = sync_api.chromium.launch_persistent_context(
            str(profile), channel="chrome", headless=True, viewport=None
        )
    except Exception as exc:
        playwright.stop()
        pytest.skip(f"系统 Chrome 不可用：{exc}")
    yield context
    context.close()
    playwright.stop()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()


@pytest.fixture
def browser_project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    project = tmp_path / "projects" / "demo"
    (project / "browser" / "flows").mkdir(parents=True)
    (project / ".env").write_text(
        "WEB=http://localhost\nAPI=http://localhost/api\nUSER=admin\nPASS=secret\n",
        encoding="utf-8",
    )
    (project / "browser" / "browser.yaml").write_text(DEFAULT_BROWSER_YAML, encoding="utf-8")
    (project / "browser" / "flows" / "smoke.yaml").write_text(DEFAULT_FLOW_YAML, encoding="utf-8")
    return project
```

- [ ] **Step 3: 写失败的配置测试**

Create `tests/test_browser_config.py`:

```python
from pathlib import Path

import pytest

from runtime.browser.config import (
    BrowserConfigError,
    list_flows,
    load_browser_config,
    load_flow,
    profile_path,
    resolve_variables,
)


def test_loads_env_login_and_defaults(browser_project):
    cfg = load_browser_config("demo")
    assert cfg.project == "demo"
    assert cfg.default_env == "dev"
    assert cfg.timeout_ms == 12000
    assert cfg.headless is False
    assert cfg.envs["dev"].base_url == "http://localhost"
    assert cfg.envs["dev"].values["api"] == "http://localhost/api"
    assert cfg.login.username == "admin"
    assert cfg.login.success_url_path == "/index"
    assert cfg.login.success_localstorage == {"Admin-Token": ".+"}


def test_project_mismatch_raises(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("project: demo", "project: other"), encoding="utf-8")
    with pytest.raises(BrowserConfigError, match="project"):
        load_browser_config("demo")


def test_unknown_browser_field_raises(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\nunknown: 1\n", encoding="utf-8")
    with pytest.raises(BrowserConfigError, match="unknown"):
        load_browser_config("demo")


def test_login_steps_and_impl_conflict_raises(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  steps:\n", "  impl: scripts/login.py:run\n  steps:\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(BrowserConfigError, match="steps"):
        load_browser_config("demo")


def test_resolve_variables_precedence(browser_project):
    cfg = load_browser_config("demo")
    flow = load_flow("demo", "smoke")
    values = resolve_variables(cfg, flow, "dev", {"order_no": "A1"}, {"EXTRA": "x"})
    assert values["order_no"] == "A1"
    assert values["BASE_URL"] == "http://localhost"
    assert values["api"] == "http://localhost/api"
    assert values["EXTRA"] == "x"


def test_missing_required_variable_lists_name(browser_project):
    cfg = load_browser_config("demo")
    flow = load_flow("demo", "smoke")
    with pytest.raises(BrowserConfigError, match="order_no"):
        resolve_variables(cfg, flow, "dev", {})


def test_flow_name_must_match_filename(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("flow: smoke", "flow: other"), encoding="utf-8")
    with pytest.raises(BrowserConfigError, match="flow"):
        load_flow("demo", "smoke")


def test_unknown_step_field_raises(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "    sleep: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(BrowserConfigError, match="sleep"):
        load_flow("demo", "smoke")


def test_login_url_can_use_base_url_placeholder(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("${WEB}/login", "${BASE_URL}/login"),
        encoding="utf-8",
    )
    cfg = load_browser_config("demo")
    assert cfg.login.url == "${BASE_URL}/login"


def test_profile_path_is_per_project_and_env(browser_project, tmp_path):
    cfg = load_browser_config("demo")
    assert profile_path(cfg, "dev") == tmp_path / "browser" / "profiles" / "demo" / "dev"
    assert profile_path(cfg, "dev", Path("custom")) == Path("custom")


def test_list_flows(browser_project):
    flows = list_flows("demo")
    assert [flow.name for flow in flows] == ["smoke"]
    assert flows[0].vars["order_no"].required is True
```

- [ ] **Step 4: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.browser'`。

- [ ] **Step 5: 实现 `runtime/browser/config.py`**

Create `runtime/browser/__init__.py`:

```python
"""浏览器测试执行引擎。"""
```

Create `runtime/browser/config.py`，实现上面的接口。关键点：

- 用 `yaml.safe_load` 读取 `project_dir(project_id) / "browser" / "browser.yaml"`，文件不存在或 YAML 非法都抛 `BrowserConfigError`。
- 允许的顶层字段：`version`、`project`、`envs`、`defaults`、`login`；其余字段报错。
- `envs` 每项的值先与 `os.environ`、`load_env(project_dir(project_id) / ".env")` 合并（`.env` 覆盖同名系统变量），再调用 `substitute`；`base_url` 必填。
- `defaults` 允许 `env`、`timeout_ms`、`headless`、`profile`；`default_env` 默认 `dev`，必须存在于 `envs`。
- `login` 中 `steps` 与 `impl` 互斥；`success` 至少一项。解析 `login.url` 时给变量表注入 `BASE_URL` 的字面量 `"${BASE_URL}"`，让具体环境留到运行时解析；`login.steps` 保持原样，由运行时替换。
- 流程文件路径 `project_dir(project_id) / "browser" / "flows" / f"{flow_name}.yaml"`；不存在抛 `FlowNotFoundError`。
- 流程允许的顶层字段：`version`、`flow`、`description`、`env`、`vars`、`steps`。
- 步骤允许的顶层字段：`name`、`timeout`、`optional`、`value`、`as`，以及动作键 `goto/click/fill/press/select/check/hover/use_row/impl` 和以 `wait_`、`expect_` 开头的键。
- 每个步骤必须有唯一 `name`，且恰好一个动作键；`fill`/`select` 必须有 `value`；否则报错。登录步骤只校验动作键，不要求 `name`。
- `resolve_variables` 按 **cli_vars > flow.vars.default > env.values + BASE_URL > os_env** 合并，然后对每个值调用 `substitute`；必填缺失时把键名放进错误消息；非必填且无默认值的变量设为空串。
- `profile_path` 默认 `data_home() / "browser" / "profiles" / cfg.project / env_name`。
- `list_flows` 遍历 `flows/*.yaml` 并调用 `load_flow`，按名称排序。

- [ ] **Step 6: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_config.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add requirements.txt runtime/browser/__init__.py runtime/browser/config.py tests/conftest.py tests/test_browser_config.py
git commit -m "$(cat <<'EOF'
feat: 增加浏览器配置与流程校验
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 定位器

**Files:**
- Create: `runtime/browser/locator.py`
- Create: `tests/browser_fixture/index.html`
- Create: `tests/browser_fixture/api/save`
- Create: `tests/browser_fixture/api/list`
- Create: `tests/browser_fixture/login.html`
- Create: `tests/test_browser_locator.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `LocatorError(Exception)`
  - `LocatorMatchError(Exception)`，带 `count: int`、`candidates: list[str]`
  - `LocatorSpec(kind: str, value: str, name: str | None, exact: bool, last: bool, within: str | None)`
  - `parse_locator(spec: dict) -> LocatorSpec`
  - `describe_locator(spec: LocatorSpec) -> str`
  - `find(scope: Any, spec: dict, aliases: dict[str, Any]) -> Any`

- [ ] **Step 1: 创建浏览器夹具页面**

Create `tests/browser_fixture/index.html`:

```html
<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>浏览器测试夹具</title></head>
<body>
  <button data-testid="save">保存</button>
  <button data-testid="dialog-opener">打开弹框</button>
  <div class="el-message" hidden>保存成功</div>
  <input placeholder="手机号">
  <input placeholder="密码">
  <div role="tab" id="tab-send">待发货</div>
  <table>
    <tbody>
      <tr>
        <td><input class="standard-checkbox" type="checkbox"></td>
        <td>WO001</td>
        <td><button data-row="WO001">更多</button></td>
        <td><button data-row="WO001">日志</button></td>
      </tr>
      <tr>
        <td><input class="standard-checkbox" type="checkbox"></td>
        <td>WO002</td>
        <td><button data-row="WO002">更多</button></td>
        <td><button data-row="WO002">日志</button></td>
      </tr>
    </tbody>
  </table>
  <div role="dialog" data-testid="dialog" hidden>物流方式<button>取消</button></div>
  <div id="log"></div>
  <script>
    const log = (text) => { document.querySelector('#log').textContent = text; };
    document.querySelector('[data-testid="save"]').addEventListener('click', async () => {
      await fetch('/api/save');
      document.querySelector('.el-message').hidden = false;
    });
    document.querySelector('[data-testid="dialog-opener"]').addEventListener('click', () => {
      document.querySelector('[data-testid="dialog"]').hidden = false;
    });
    document.querySelector('#tab-send').addEventListener('click', async () => {
      await fetch('/api/list');
      log('list-loaded');
    });
    document.querySelectorAll('table button').forEach((btn) => {
      btn.addEventListener('click', () => log(`${btn.dataset.row}-${btn.textContent}`));
    });
  </script>
</body>
</html>
```

Create `tests/browser_fixture/api/save` 和 `tests/browser_fixture/api/list`，内容均为 `{}`。

Create `tests/browser_fixture/login.html`:

```html
<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>登录</title></head>
<body>
  <button>登 录</button>
  <script>
    document.querySelector('button').addEventListener('click', () => {
      localStorage.setItem('Admin-Token', 'token-123');
      location.href = '/index.html';
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: 写失败的定位器测试**

Create `tests/test_browser_locator.py`:

```python
import pytest

from runtime.browser.locator import (
    LocatorError,
    LocatorMatchError,
    describe_locator,
    find,
    parse_locator,
)


def test_parse_each_kind():
    assert parse_locator({"testid": "save"}).kind == "testid"
    assert parse_locator({"css": "table tbody tr"}).value == "table tbody tr"
    assert parse_locator({"placeholder": "手机号"}).kind == "placeholder"
    role = parse_locator({"role": "button", "name": "搜索", "exact": True})
    assert (role.kind, role.value, role.name, role.exact) == ("role", "button", "搜索", True)
    assert parse_locator({"text": "更多", "last": True}).last is True


def test_parse_requires_role_name():
    with pytest.raises(LocatorError, match="name"):
        parse_locator({"role": "button"})


def test_parse_rejects_two_kinds():
    with pytest.raises(LocatorError, match="只能"):
        parse_locator({"css": "#a", "text": "a"})


def test_describe_locator():
    assert describe_locator(parse_locator({"testid": "save"})) == "testid=save"


def test_find_by_testid_text_role_css(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    assert find(page, {"testid": "save"}, {}).inner_text() == "保存"
    assert find(page, {"text": "WO001"}, {}).inner_text() == "WO001"
    assert find(page, {"css": "[data-testid=dialog]"}, {}).count() == 1
    assert find(page, {"role": "tab", "name": "待发货"}, {}).inner_text() == "待发货"


def test_find_within_alias(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    row = page.locator("table tbody tr").filter(has_text="WO001")
    assert find(page, {"in": "row", "role": "button", "name": "更多"}, {"row": row}).get_attribute("data-row") == "WO001"


def test_find_rejects_multiple_matches_with_candidates(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    with pytest.raises(LocatorMatchError) as exc:
        find(page, {"role": "button", "name": "更多"}, {})
    assert exc.value.count == 2
    assert any("WO001" in text for text in exc.value.candidates)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_locator.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.browser.locator'`；浏览器用例在依赖未就绪时跳过。

- [ ] **Step 4: 实现 `runtime/browser/locator.py`**

关键点：

- `parse_locator` 只允许 `testid`、`role`、`text`、`placeholder`、`css` 中恰好一个；`role` 必须有 `name`；允许 `exact`、`last`、`in`。
- `find` 先按 `in` 取 `aliases[alias]` 作为 scope，再用 Playwright 对应方法构造 locator。
- 若匹配数大于 1 且 `last` 为假，抛 `LocatorMatchError`，`candidates` 取前 5 个元素的 `closest('tr')?.innerText || innerText`。
- `last` 为真时返回 `.last`，否则返回 `.first`；0 个匹配不抛错，交给后续等待或动作超时。
- `describe_locator` 输出 `kind=value`，role 输出 `role=button[name=搜索]`。

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_locator.py -v`
Expected: PASS；若机器没有 Chrome，浏览器用例显示 skipped。

- [ ] **Step 6: 提交**

```bash
git add runtime/browser/locator.py tests/browser_fixture tests/test_browser_locator.py
git commit -m "$(cat <<'EOF'
feat: 增加浏览器统一定位器
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Chrome 驱动与登录态检测

**Files:**
- Create: `runtime/browser/driver.py`
- Create: `tests/test_browser_driver.py`

**Interfaces:**
- Consumes: `runtime.browser.config.LoginConfig`。
- Produces:
  - `BrowserEnvError(Exception)`
  - `BrowserSession(playwright: Any, context: Any, page: Any)`
  - `launch(headless: bool, profile: Path, *, tracing: bool = False) -> BrowserSession`
  - `close(session: BrowserSession, trace_path: Path | None = None) -> None`
  - `check_login_success(page: Any, login: LoginConfig) -> bool`

- [ ] **Step 1: 写失败的驱动测试**

Create `tests/test_browser_driver.py`:

```python
from pathlib import Path

import pytest

from runtime.browser.config import LoginConfig
from runtime.browser.driver import BrowserEnvError, check_login_success, close, launch


def test_launch_and_close(tmp_path, fixture_url):
    session = launch(headless=True, profile=tmp_path / "profile")
    try:
        session.page.goto(fixture_url + "/index.html")
        assert "浏览器测试夹具" in session.page.title()
    finally:
        close(session)


def test_second_launch_on_same_profile_reports_actionable_error(tmp_path):
    profile = tmp_path / "profile"
    first = launch(headless=True, profile=profile)
    try:
        with pytest.raises(BrowserEnvError, match="profile"):
            launch(headless=True, profile=profile)
    finally:
        close(first)


def test_login_success_ignores_query_string(page, fixture_url):
    login = LoginConfig(
        url=fixture_url + "/login.html",
        username=None,
        password=None,
        steps=[],
        impl=None,
        success_url_path="/index.html",
        success_localstorage={},
    )
    page.goto(fixture_url + "/login.html?redirect=/index.html")
    page.evaluate("localStorage.clear()")
    assert check_login_success(page, login) is False
    page.goto(fixture_url + "/index.html")
    assert check_login_success(page, login) is True


def test_login_success_checks_local_storage(page, fixture_url):
    login = LoginConfig(
        url=fixture_url + "/login.html",
        username=None,
        password=None,
        steps=[],
        impl=None,
        success_url_path=None,
        success_localstorage={"Admin-Token": r"token-\d+"},
    )
    page.goto(fixture_url + "/login.html")
    page.evaluate("localStorage.clear()")
    assert check_login_success(page, login) is False
    page.evaluate("localStorage.setItem('Admin-Token', 'token-123')")
    assert check_login_success(page, login) is True
    page.evaluate("localStorage.setItem('Admin-Token', 'wrong')")
    assert check_login_success(page, login) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_driver.py -v`
Expected: FAIL，`No module named 'runtime.browser.driver'`。

- [ ] **Step 3: 实现 `runtime/browser/driver.py`**

关键点：

- `launch` 用 `sync_playwright().start()`，再 `chromium.launch_persistent_context(str(profile), channel="chrome", headless=headless, viewport=None, accept_downloads=True)`；`tracing=True` 时启动 `context.tracing.start(screenshots=True, snapshots=True, sources=True)`。
- 异常包装成 `BrowserEnvError`，消息包含 profile 路径和「关闭占用该 profile 的 Chrome，或换 --profile」。
- `close` 先按需 `context.tracing.stop(path=str(trace_path))`，再 `context.close()`、`playwright.stop()`；任一步失败不掩盖原异常。
- `check_login_success`：`success_url_path` 用 `urlparse(page.url).path == path`；`success_localstorage` 逐项 `localStorage.getItem` 后 `re.search`；配置了多项时全部满足才返回 True。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_driver.py -v`
Expected: PASS；无 Chrome 时 skipped。

- [ ] **Step 5: 提交**

```bash
git add runtime/browser/driver.py tests/test_browser_driver.py
git commit -m "$(cat <<'EOF'
feat: 增加 Chrome 驱动与登录态检测
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 流程执行

**Files:**
- Create: `runtime/browser/flow.py`
- Create: `tests/test_browser_flow.py`

**Interfaces:**
- Consumes: `runtime.browser.config.FlowDef`, `BrowserConfig`, `EnvConfig`, `LoginConfig`；`runtime.browser.driver.check_login_success`；`runtime.browser.locator.find`。
- Produces:
  - `FlowRunError(Exception)`
  - `StepResult(name: str, status: str, duration_ms: int, error: str | None = None)`
  - `StepFailure(step_index: int, step_name: str, message: str, expected: str | None, actual: str | None, detail: dict)`
  - `FlowResult(flow: str, env: str, result: str, started_at: str, duration_ms: int, flow_file: str, steps: list[StepResult], failure: StepFailure | None = None, artifacts: str | None = None, error: str | None = None)`
  - `run_flow(page: Any, flow: FlowDef, env_name: str, variables: dict[str, str], project_dir: Path, *, timeout_ms: int = 15000, logger: Any = None) -> FlowResult`
  - `ensure_login(page: Any, login: LoginConfig, *, variables: dict[str, str], project_dir: Path, timeout_ms: int = 15000, logger: Any = None) -> bool`
  - `run_step(page: Any, step: dict, variables: dict[str, str], aliases: dict[str, Any], project_dir: Path, *, timeout_ms: int, logger: Any = None) -> None`
  - `load_impl(spec: str, root: Path) -> Callable`

- [ ] **Step 1: 写失败的流程测试**

Create `tests/test_browser_flow.py`:

```python
import pytest

from pathlib import Path

from runtime.browser.config import BrowserConfig, EnvConfig, FlowDef, LoginConfig, VarDef
from runtime.browser.flow import FlowRunError, ensure_login, run_flow


def make_flow(*steps):
    return FlowDef(
        name="test",
        description="",
        env="dev",
        vars={"order_no": VarDef(True, None, "")},
        steps=list(steps),
        path=Path("test.yaml"),
    )


def run(page, tmp_path, flow, variables=None, timeout_ms=1000):
    return run_flow(
        page, flow, "dev", {"order_no": "WO001", **(variables or {})},
        tmp_path, timeout_ms=timeout_ms,
    )


def test_click_fill_wait_and_expect(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "保存", "click": {"testid": "save"}, "wait_response": "/api/save",
         "expect_visible": {"css": ".el-message"}},
        {"name": "填手机号", "fill": {"placeholder": "手机号"}, "value": "13800000000"},
        {"name": "断言", "expect_text": {"locator": {"css": ".el-message"}, "contains": "保存成功"}},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "pass"
    assert [step.status for step in result.steps] == ["pass", "pass", "pass", "pass"]


def test_wait_response_on_tab_click(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "切页签", "click": {"role": "tab", "name": "待发货"},
         "wait_response": "/api/list"},
        {"name": "检查", "expect_text": {"locator": {"css": "#log"}, "contains": "list-loaded"}},
    )
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_url_hidden_and_count(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "地址", "expect_url": {"path": "/index.html"}},
        {"name": "隐藏", "expect_hidden": {"css": ".el-message"}},
        {"name": "计数", "expect_count": {"locator": {"css": "table tbody tr"}, "eq": 2}},
    )
    assert run(page, tmp_path, flow).result == "pass"


def test_use_row_scopes_actions(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "定位行", "use_row": {"text": "${order_no}", "checkbox": "input.standard-checkbox"},
         "as": "row", "wait_visible": True},
        {"name": "点更多", "click": {"in": "row", "role": "button", "name": "更多"}},
        {"name": "检查", "expect_text": {"locator": {"css": "#log"}, "contains": "WO001-更多"}},
    )
    assert run(page, tmp_path, flow).result == "pass"


def test_impl_merges_vars(page, fixture_url, tmp_path):
    (tmp_path / "hook.py").write_text(
        "def go(ctx):\n"
        "    ctx.page.evaluate(\"document.querySelector('#log').textContent = 'impl-ok'\")\n"
        "    return {'impl_value': '42'}\n"
        "def check(ctx):\n"
        "    assert ctx.vars['impl_value'] == '42'\n",
        encoding="utf-8",
    )
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "调用", "impl": "hook.py:go"},
        {"name": "检查", "impl": "hook.py:check"},
        {"name": "看结果", "expect_text": {"locator": {"css": "#log"}, "contains": "impl-ok"}},
    )
    assert run(page, tmp_path, flow).result == "pass"


def test_optional_step_is_skipped(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "不存在", "click": {"testid": "nope"}, "optional": True},
        {"name": "继续", "expect_visible": {"css": "#log"}},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "pass"
    assert result.steps[1].status == "skipped"


def test_failure_reports_step_and_expected_actual(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "找不到", "expect_text": {"locator": {"css": "#log"}, "contains": "不存在"}},
    )
    result = run(page, tmp_path, flow, timeout_ms=300)
    assert result.result == "fail"
    assert result.failure.step_name == "找不到"
    assert "不存在" in result.failure.expected
    assert result.failure.actual is not None


def test_ensure_login_skips_when_already_logged_in(page, fixture_url, tmp_path):
    login = LoginConfig(
        url=fixture_url + "/index.html", username=None, password=None,
        steps=[{"click": {"testid": "nope"}}], impl=None,
        success_url_path="/index.html", success_localstorage={},
    )
    assert ensure_login(page, login, variables={}, project_dir=tmp_path, timeout_ms=300) is True


def test_ensure_login_runs_steps_then_verifies(page, fixture_url, tmp_path):
    page.goto(fixture_url + "/login.html")
    login = LoginConfig(
        url=fixture_url + "/login.html", username=None, password=None,
        steps=[{"click": {"role": "button", "name": "登 录"}}], impl=None,
        success_url_path="/index.html", success_localstorage={"Admin-Token": r"token-\d+"},
    )
    assert ensure_login(page, login, variables={}, project_dir=tmp_path, timeout_ms=1000) is True


def test_ensure_login_fails_when_success_missing(page, fixture_url, tmp_path):
    login = LoginConfig(
        url=fixture_url + "/login.html", username=None, password=None,
        steps=[{"click": {"role": "button", "name": "登 录"}}], impl=None,
        success_url_path="/never", success_localstorage={},
    )
    with pytest.raises(FlowRunError, match="登录"):
        ensure_login(page, login, variables={}, project_dir=tmp_path, timeout_ms=300)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_flow.py -v`
Expected: FAIL，`No module named 'runtime.browser.flow'`。

- [ ] **Step 3: 实现 `runtime/browser/flow.py`**

关键点：

- `run_flow` 复制传入变量，逐步执行；每步计时并写入 `StepResult`；异常转成 `StepFailure` 后停止，返回 `result="fail"`。
- `run_step` 先 `substitute(step, variables)`；按动作键执行。
- `wait_response` 用 `page.expect_response(predicate)` 包住动作：字符串匹配 URL 且状态 200–299；字典支持 `url_contains`、`status`。
- `use_row`：`page.locator(step["use_row"].get("row_css", "table tbody tr"))`，有 `checkbox` 时 `.filter(has=page.locator(checkbox))`，再 `.filter(has_text=text)`；存 `aliases[as]`；`wait_visible: true` 时等别名可见。
- `impl`：`load_impl` 按 `project_dir` 解析，调用 `func(ctx)`，返回 dict 合并进变量；`ctx` 用 `SimpleNamespace(page=..., vars=..., project_dir=..., data_home=..., logger=..., step=...)`。
- `optional: true` 的动作先 `locator.count()`；为 0 时把本步标为 `skipped`，不执行等待与断言。
- 等待与断言用 `_poll(predicate, timeout_ms)`，每 50ms 检查一次；`expect_url` 比较 pathname，`expect_hidden` 用 `state="hidden"`，`expect_count` 用 `locator.count()` 比较 `eq`/`min`/`max`；`expect_text` 记录实际 `inner_text` 到失败信息。
- `ensure_login`：先用 `substitute(login.url, variables)` 解析地址，`page.goto` 后轮询 `check_login_success` 最多 3 秒；不成功则把 `login.username`/`login.password` 以 `username`/`password` 加入变量副本，执行登录步骤（缺 `name` 的补 `登录步骤N`）；`login.impl` 存在时改为调用该函数；再轮询最多 `timeout_ms`；仍失败抛 `FlowRunError`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_flow.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add runtime/browser/flow.py tests/test_browser_flow.py
git commit -m "$(cat <<'EOF'
feat: 增加浏览器流程执行引擎
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 报告与诊断包

**Files:**
- Create: `runtime/browser/report.py`
- Create: `runtime/browser/diagnose.py`
- Create: `tests/test_browser_report.py`

**Interfaces:**
- Consumes: `runtime.browser.flow.FlowResult`, `FlowDef`。
- Produces:
  - `report.timestamp() -> str`
  - `report.reports_dir(project_id: str) -> Path`
  - `report.artifacts_dir(project_id: str) -> Path`
  - `report.write_report(project_id: str, result: FlowResult) -> Path`
  - `report.prune(root: Path, keep: int = 20) -> None`
  - `diagnose.PageCollector`，属性 `requests: list[dict]`、`console: list[str]`，方法 `attach(page) -> None`
  - `diagnose.redact_headers(headers: dict[str, str]) -> dict[str, str]`
  - `diagnose._screenshot(page, path: Path) -> None`（单独封装，便于测试截图失败）
  - `diagnose.capture(page, project_id: str, flow: FlowDef, result: FlowResult, collector: PageCollector, *, trace_path: Path | None = None) -> Path`

- [ ] **Step 1: 写失败的报告与诊断测试**

Create `tests/test_browser_report.py`:

```python
import json
from pathlib import Path

from runtime.browser.config import FlowDef, VarDef
from runtime.browser.diagnose import PageCollector, capture, redact_headers
from runtime.browser.flow import FlowResult, StepFailure, StepResult
from runtime.browser.report import prune, write_report


def failed_result(flow_file: Path) -> FlowResult:
    return FlowResult(
        flow="smoke", env="dev", result="fail",
        started_at="2026-11-03T10:00:00+08:00", duration_ms=120,
        flow_file=str(flow_file),
        steps=[StepResult("打开", "pass", 50), StepResult("断言", "fail", 70, "文本不匹配")],
        failure=StepFailure(1, "断言", "文本不匹配", expected="不存在", actual="list-loaded", detail={}),
    )


def test_write_report_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    flow_file = tmp_path / "smoke.yaml"
    flow_file.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    for _ in range(3):
        write_report("demo", failed_result(flow_file))
    reports = sorted((tmp_path / "browser" / "reports").glob("*.json"))
    assert len(reports) == 3
    prune(tmp_path / "browser" / "reports", keep=2)
    assert len(list((tmp_path / "browser" / "reports").glob("*.json"))) == 2
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert data["failure"]["step_name"] == "断言"


def test_redact_headers():
    cleaned = redact_headers({"Authorization": "x", "Cookie": "y", "Accept": "json"})
    assert cleaned == {"Accept": "json"}


def test_capture_writes_diagnosis_package(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    collector = PageCollector()
    collector.attach(page)
    flow = FlowDef("smoke", "", "dev", {"order_no": VarDef(True, None, "")}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    result = failed_result(flow.path)
    out = capture(page, "demo", flow, result, collector)
    for name in ["diagnosis.md", "failure.png", "page.html", "requests.json", "console.log", "flow.snapshot.yaml", "run.log"]:
        assert (out / name).exists(), name
    text = (out / "diagnosis.md").read_text(encoding="utf-8")
    assert "断言" in text and "不存在" in text


def test_capture_survives_screenshot_failure(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    flow = FlowDef("smoke", "", "dev", {}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")

    def broken(*args, **kwargs):
        raise RuntimeError("page crashed")

    monkeypatch.setattr("runtime.browser.diagnose._screenshot", broken)
    out = capture(page, "demo", flow, failed_result(flow.path), PageCollector())
    assert (out / "diagnosis.md").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_report.py -v`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `report.py` 与 `diagnose.py`**

关键点：

- `timestamp` 返回 `YYYYMMDD-HHMMSS-毫秒`。
- `write_report` 用 `dataclasses.asdict` 写 JSON，路径 `reports_dir / f"{result.flow}-{timestamp}.json"`；同名时追加 `-2`、`-3` 保证唯一；写完调用 `prune`。`StepFailure.detail` 只放可 JSON 序列化的内容（字符串、数字、列表、字典）。
- `prune` 按名称倒序保留最新 `keep` 个；`capture` 结束时同样对 artifacts 目录调用 `prune`。
- `PageCollector.attach` 监听 `response`，记录 `method`、`url`、`status`、`request_headers`（经 `redact_headers`）；监听 `console` 记录 `type: text`。
- `capture` 创建 `.data-tools/browser/artifacts/<flow>-<timestamp>/`，逐项写文件，每项独立 `try/except`；截图失败也继续写 `diagnosis.md`。
- `diagnosis.md` 包含失败步骤与序号、期望、实际、当前 URL、标题、请求数、console 数、建议动作。
- `run.log` 写每步状态与耗时；`trace_path` 存在时复制为 `trace.zip`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_report.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add runtime/browser/report.py runtime/browser/diagnose.py tests/test_browser_report.py
git commit -m "$(cat <<'EOF'
feat: 增加浏览器报告与诊断包
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: CLI

**Files:**
- Create: `scripts/browser.py`
- Create: `tests/test_browser_cli.py`

**Interfaces:**
- Consumes: Task 1–5 的全部接口。
- Produces:
  - 退出码常量 `PASS=0`、`FLOW_FAIL=1`、`CONFIG_ERROR=2`、`FLOW_NOT_FOUND=3`、`ENV_ERROR=4`
  - `main(argv: list[str] | None = None) -> int`
  - 子命令 `doctor`、`list`、`run`、`probe`、`diagnose`

- [ ] **Step 1: 写失败的 CLI 测试**

Create `tests/test_browser_cli.py`:

```python
import subprocess
import sys
from pathlib import Path

from runtime.browser.config import BrowserConfig, EnvConfig, FlowDef, VarDef
from runtime.browser.flow import FlowResult, StepResult
from scripts import browser as cli


def fake_config():
    return BrowserConfig(
        project="demo",
        envs={"dev": EnvConfig("dev", "http://localhost", {"api": "http://localhost/api"})},
        default_env="dev", timeout_ms=1000, headless=False, profile=None, login=None,
    )


def fake_flow():
    return FlowDef("smoke", "", "dev", {"order_no": VarDef(True, None, "")}, [], Path("smoke.yaml"))


def test_help_runs_outside_pytest(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "browser.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert out.returncode == 0, out.stderr


def test_list_prints_flows(browser_project, capsys):
    assert cli.main(["list", "--project", "demo"]) == 0
    assert "smoke" in capsys.readouterr().out


def test_missing_flow_returns_3(browser_project):
    assert cli.main(["run", "--project", "demo", "--flow", "nope"]) == 3


def test_config_error_returns_2(browser_project):
    (browser_project / "browser" / "browser.yaml").write_text("version: 1\n", encoding="utf-8")
    assert cli.main(["run", "--project", "demo", "--flow", "smoke"]) == 2


def test_doctor_missing_config_returns_2(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    assert cli.main(["doctor", "--project", "demo"]) == 2


class _Session:
    page = object()


class _Collector:
    def attach(self, page):
        pass


def test_run_success_writes_report_and_returns_0(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(cli, "resolve_project", lambda project: project)
    monkeypatch.setattr(cli, "load_browser_config", lambda project: fake_config())
    monkeypatch.setattr(cli, "load_flow", lambda project, flow: fake_flow())
    monkeypatch.setattr(cli, "launch", lambda headless, profile, tracing=False: _Session())
    monkeypatch.setattr(cli, "PageCollector", _Collector)
    monkeypatch.setattr(cli, "ensure_login", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli, "run_flow",
        lambda *args, **kwargs: FlowResult("smoke", "dev", "pass", "now", 1, "smoke.yaml", [StepResult("打开", "pass", 1)]),
    )
    monkeypatch.setattr(cli, "write_report", lambda project, result: calls.setdefault("report", Path("report.json")))
    monkeypatch.setattr(cli, "close", lambda *args, **kwargs: None)
    assert cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1"]) == 0
    assert "report" in calls


def test_run_failure_captures_diagnostics_and_returns_1(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(cli, "resolve_project", lambda project: project)
    monkeypatch.setattr(cli, "load_browser_config", lambda project: fake_config())
    monkeypatch.setattr(cli, "load_flow", lambda project, flow: fake_flow())
    monkeypatch.setattr(cli, "launch", lambda headless, profile, tracing=False: _Session())
    monkeypatch.setattr(cli, "PageCollector", _Collector)
    monkeypatch.setattr(cli, "ensure_login", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli, "run_flow",
        lambda *args, **kwargs: FlowResult("smoke", "dev", "fail", "now", 1, "smoke.yaml", [StepResult("断言", "fail", 1, "x")]),
    )
    monkeypatch.setattr(cli, "capture", lambda *args, **kwargs: captured.setdefault("artifacts", Path("artifacts")))
    monkeypatch.setattr(cli, "write_report", lambda project, result: Path("report.json"))
    monkeypatch.setattr(cli, "close", lambda *args, **kwargs: None)
    assert cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1"]) == 1
    assert "artifacts" in captured
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_cli.py -v`
Expected: FAIL，`No module named 'scripts.browser'`。

- [ ] **Step 3: 实现 `scripts/browser.py`**

关键点：

- 按 `scripts/run.py` 的写法插入仓库根到 `sys.path`，并 `sys.stdout.reconfigure(encoding="utf-8")`（存在时）。
- `argparse` 子命令；`--var` 用 `action="append"`，按第一个 `=` 拆分，格式错误返回 `2`。
- `doctor`：先检查配置文件存在且可解析，缺失或非法直接返回 `2`；再检查 Python 版本、Playwright 导入、Chrome 可执行路径（`shutil.which("chrome")` 或两个 Program Files 路径）、profile 目录可写、`browser.yaml` 中 `${VAR}` 与 `.env` 的键名差异（忽略运行时计算的 `BASE_URL`），环境问题返回 `4`。
- `list`：调用 `list_flows`，打印名称、描述、默认 env、必填变量；`--json` 输出列表。
- `run`：解析项目、配置、流程、变量；`FlowNotFoundError` 返回 `3`，其它 `BrowserConfigError` 返回 `2`；`--profile` 覆盖 profile 路径；`--json` 输出报告 JSON；`launch` → `PageCollector.attach` → `ensure_login` → `run_flow`；`ensure_login` 抛 `FlowRunError` 按环境错误返回 `4`；失败时先 `capture`、把路径写入 `result.artifacts`，再 `write_report`；`finally close`；按结果返回 `0/1/4`。
- `probe`：启动浏览器，`login` 存在时先登录，打开 URL，等待 `load`，最多等 2 秒网络空闲（`page.wait_for_load_state("networkidle", timeout=2000)` 失败也继续），写 `probe.md`、`page.png`、`page.html`、`elements.json`、`requests.json`、`console.log` 到 `.data-tools/browser/probes/`。`elements.json` 结构为 `{"buttons": [{"text", "testid", "role"}], "inputs": [{"placeholder", "testid"}], "rows": [{"text"}]}`。
- `diagnose`：读最近一份 artifacts 的 `diagnosis.md` 并打印；没有返回 `2`。
- `--trace` 时给 `launch` 传 `tracing=True`，trace 路径放 artifacts 目录。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_browser_cli.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/browser.py tests/test_browser_cli.py
git commit -m "$(cat <<'EOF'
feat: 增加浏览器测试命令行
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 技能、参考文档与模板

**Files:**
- Create: `skills/browser-test/SKILL.md`
- Create: `skills/_references/browser-flow-contract.md`
- Create: `skills/_references/browser-diagnosis.md`
- Create: `skills/_TEMPLATE/browser.example.yaml`
- Create: `skills/_TEMPLATE/browser-flow.example.yaml`
- Modify: `skills/_references/trigger-routing.md`
- Modify: `skills/_references/project-layout.md`
- Modify: `tests/test_skills.py`
- Modify: `README.md`
- Modify: `docs/usage.md`

**Interfaces:**
- Consumes: CLI 与 DSL 契约（Task 1–6）。
- Produces: 可被 `install.py` / `sync_project.py` 自动发现的第 6 个技能目录。

- [ ] **Step 1: 写失败的技能测试**

Modify `tests/test_skills.py`：把三个参数化列表都加上 `browser-test`，并追加：

```python
def test_browser_skill_memory_and_safety_rules():
    text = (SKILLS / "browser-test" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["不写固定 sleep", "probe", "diagnosis.md", "pitfalls.md", "退出码 0", "browser.py"]:
        assert word in text


def test_browser_examples_parse():
    browser_cfg = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "browser.example.yaml").read_text(encoding="utf-8")
    )
    flow = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "browser-flow.example.yaml").read_text(encoding="utf-8")
    )
    assert browser_cfg["version"] == 1 and "login" in browser_cfg
    assert flow["version"] == 1 and flow["steps"]


def test_trigger_routing_includes_browser():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    assert "浏览器" in text and "browser-test" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py -v`
Expected: FAIL，找不到 `skills/browser-test/SKILL.md` 和模板。

- [ ] **Step 3: 写 `SKILL.md`**

内容必须包含：

- frontmatter `name: browser-test` 与触发描述（测一下、走一遍、浏览器验证、点一遍、复现一下、回归）。
- `## 适用场景`、`## 第 0 步：环境检查`、`## 前置检查`、`## 执行`、`## 失败处理`、`## 记忆规则`。
- 第 0 步与现有 5 个技能一致：定位 `<TOOLS_DIR>` / `<DATA_HOME>`、Python 3.11+、bootstrap、`update.ps1 -CheckOnly -Quiet`。
- 执行顺序：`list` 查已有流程 → 有就 `run`；没有就 `probe` → 写 YAML → `run`。
- 铁律：先查流程与坑库、不写固定 sleep、选择器唯一、一条流程一次连接、业务逻辑只进项目 `scripts/`。
- 失败处理表：退出码 2/3/4 分别怎么处理；失败后读 `diagnosis.md` 自愈，只以退出码 0 报通过。
- 记忆规则：流程、坑库提交；`.data-tools/browser/` 不提交；凭据只放 `.env`。
- 命令块保持单行，不留反斜杠续行。

- [ ] **Step 4: 写参考文档与模板**

- `browser-flow-contract.md`：完整复制设计文档第 5–7 节的 `browser.yaml`、DSL、变量解析规则，附一个完整示例。
- `browser-diagnosis.md`：诊断包文件清单、`diagnosis.md` 字段、自愈循环、坑库四段式格式。
- `browser.example.yaml`：与设计文档第 5 节一致，凭据用 `${VAR}`。
- `browser-flow.example.yaml`：B2D 待发货示例流程（设计文档 6.7）。
- `trigger-routing.md` 增加「浏览器测试 → browser-test」一行。
- `project-layout.md` 增加 `.data-tools/projects/<ID>/browser/` 与 `.data-tools/browser/` 的提交边界。
- `README.md` 技能表改为 6 个；`docs/usage.md` 目录与「五个技能怎么选」改为六个，补一节浏览器测试。

- [ ] **Step 5: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add skills/browser-test skills/_references skills/_TEMPLATE/browser.example.yaml skills/_TEMPLATE/browser-flow.example.yaml tests/test_skills.py README.md docs/usage.md
git commit -m "$(cat <<'EOF'
docs: 增加浏览器测试技能与使用文档
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 分发、忽略规则与版本

**Files:**
- Modify: `scripts/sync_project.py`
- Modify: `tests/test_sync_project.py`
- Modify: `tests/test_install.py`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: 现有 `GITIGNORE_BLOCK`、`skill_names()`。
- Produces: 业务仓库同步后包含 `.data-tools/browser/` 忽略项，且第 6 个技能可被发现。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_sync_project.py::test_upsert_gitignore_is_idempotent` 追加：

```python
    assert ".data-tools/browser/" in text
```

在 `tests/test_install.py` 追加（把首行导入改为 `from scripts.install import install, main, remove, skill_names`）：

```python
def test_skill_names_discovers_browser_test(tmp_path):
    path = tmp_path / "skills" / "browser-test"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: browser-test\ndescription: 测试\n---\n", encoding="utf-8")
    assert "browser-test" in skill_names(tmp_path)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py::test_upsert_gitignore_is_idempotent tests/test_install.py -v`
Expected: FAIL，`.data-tools/browser/` 不在忽略块中；若 `skill_names` 已导入则第二条可能直接通过。

- [ ] **Step 3: 实现分发改动**

- `scripts/sync_project.py` 的 `GITIGNORE_BLOCK` 增加一行 `.data-tools/browser/`。
- `.claude-plugin/plugin.json` 和 `.claude-plugin/marketplace.json` 的 `version` 从 `1.4.0` 改为 `1.5.0`（marketplace 的 `metadata.version` 与 `plugins[0].version` 两处都要改），描述补上「浏览器测试」。
- `README.md` 的插件描述如仍写 5 项能力，同步改为 6 项（若 Task 7 已改则跳过）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py tests/test_install.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/sync_project.py tests/test_sync_project.py tests/test_install.py .claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "$(cat <<'EOF'
feat: 分发浏览器测试能力并升级到 1.5.0
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: hexincloud 试点迁移与验收

**Files:**
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/.env.example`
- Create: `C:/project/hexincloud/.data-tools/projects/hexincloud/browser/browser.yaml`
- Create: `C:/project/hexincloud/.data-tools/projects/hexincloud/browser/flows/b2d-send.yaml`
- Create: `C:/project/hexincloud/.data-tools/projects/hexincloud/browser/pitfalls.md`
- Delete（确认后）: `C:/project/hexincloud/.claude/skills/browser-test/`
- Regenerate: `C:/project/hexincloud/.claude/skills/browser-test/SKILL.md`

**Interfaces:**
- Consumes: Task 1–8 的全部能力。
- Produces: 一条真实可复跑的 B2D 流程与迁移后的技能入口。

- [ ] **Step 1: 迁移旧技能知识**

先读现有 `C:/project/hexincloud/.claude/skills/browser-test/references/` 与 `flows/B2D待发货.md`，把内容整理成：

`browser/browser.yaml`：

```yaml
version: 1
project: hexincloud
envs:
  dev:
    base_url: ${HEXIN_WEB_URL}
  test:
    base_url: ${TEST_HEXIN_WEB_URL}
defaults:
  env: dev
login:
  url: ${BASE_URL}/login
  username: ${HEXIN_USERNAME}
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

`browser/flows/b2d-send.yaml`：按设计文档 6.7 的示例，补上「打开行日志」步骤。

`browser/pitfalls.md`：至少记录两条现有坑：

- 登录成功判断不能用 `/\/index/` 正则，登录页 `redirect` 参数含 `/index`。
- 侧边栏也有「查询」按钮，选择器要限定范围。

在 `.env.example` 增加键名（值留空）：`HEXIN_WEB_URL=`、`TEST_HEXIN_WEB_URL=`；在 `.env` 填入确认过的前端根地址（不是接口网关）。

- [ ] **Step 2: 清理旧技能并同步 claudeTool 到业务仓库**

知识已迁移后，确认并删除旧目录 `C:/project/hexincloud/.claude/skills/browser-test/`（含 `scripts/`、`references/`、`flows/`、`node_modules`），避免同步后残留旧文件。

Run: `C:/project/claudeTool/.venv/Scripts/python.exe C:/project/claudeTool/scripts/sync_project.py --project-dir C:/project/hexincloud --project-id hexincloud --targets claude`
Expected: 业务仓库生成 `data-tools/skills/browser-test/`、`data-tools/runtime/browser/`、`data-tools/scripts/browser.py`，`.gitignore` 含 `.data-tools/browser/`。

- [ ] **Step 3: 环境检查**

Run: `C:/project/hexincloud/data-tools/.venv/Scripts/python.exe C:/project/hexincloud/data-tools/scripts/browser.py doctor --project hexincloud`
Expected: Python、Playwright、Chrome、profile、配置、变量全部通过；有缺失按提示修复。

- [ ] **Step 4: 首次跑通 B2D 流程**

从页面或台账取一个真实待发货单号，执行：

```bash
C:/project/hexincloud/data-tools/.venv/Scripts/python.exe C:/project/hexincloud/data-tools/scripts/browser.py run --project hexincloud --flow b2d-send --var order_no=<真实单号>
```

Expected: 退出码 0，打印步骤数与耗时。

- [ ] **Step 5: 验证登录复用与无头**

再跑一次同一命令，Expected: 不出现登录步骤，耗时明显下降。

Run: 同一命令加 `--headless`
Expected: 退出码 0。

- [ ] **Step 6: 演练自愈**

把 `b2d-send.yaml` 中 `修改物流方式` 的选择器故意改成不存在的文本，运行：
Expected: 退出码 1，打印诊断包路径；`diagnosis.md` 含失败步骤、期望/实际、当前 URL。

读诊断包后改回选择器，重跑：
Expected: 退出码 0。

把这次现象追加到 `browser/pitfalls.md`（按「现象」去重）。

- [ ] **Step 7: 提交业务仓库**

Run: `git -C C:/project/hexincloud status`
Expected: 只出现 `.data-tools/projects/hexincloud/browser/`、`.env.example`、`data-tools/`、`.claude/skills/`、`.gitignore` 的预期改动；没有 `.env`、profile、截图、报告。

经用户确认后提交：

```bash
git -C C:/project/hexincloud add .data-tools/projects/hexincloud/browser .data-tools/projects/hexincloud/.env.example data-tools .claude/skills .gitignore
git -C C:/project/hexincloud commit -m "$(cat <<'EOF'
feat: 接入浏览器测试能力与 B2D 流程
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## 收尾验证

- [ ] **全量测试**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过；无 Chrome 的机器只跳过浏览器集成用例。

- [ ] **密钥检查**

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`
Expected: 通过，不报新增文件含凭据。

- [ ] **工作区检查**

Run: `git status`
Expected: 没有 `.data-tools/browser/`、profile、截图、报告被跟踪；没有未预期的生成物。
