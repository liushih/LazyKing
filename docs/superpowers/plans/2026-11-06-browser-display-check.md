# 浏览器显示检查实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 browser-test 增加步骤级 `expect_display` 断言：核对声明字段，并在容器内扫描截断与溢出，问题汇总后让流程失败、写入诊断包。

**Architecture:** 新增 `runtime/browser/display.py`，用页面内一段 JS 完成字段核对与截断扫描，Python 侧负责轮询、汇总和抛错；`flow.py` 接入断言，`config.py` 做启动前结构校验，`diagnose.py` 输出「显示问题」；每个任务先写夹具与失败测试，再实现。

**Tech Stack:** Python 3.11、PyYAML、Playwright（系统 Chrome）、pytest。

**Spec:** `docs/superpowers/specs/2026-11-06-browser-display-check-design.md`

## Global Constraints

- 解释器一律用 `.venv/Scripts/python.exe`；测试命令 `".venv/Scripts/python.exe" -m pytest tests -q`。
- 不新增第三方依赖。
- 进 LazyKing 仓库的内容必须与具体项目无关；消息文案沿用现有中文风格。
- 没有 `expect_display` 的流程行为必须保持不变。
- 结构非法的 `expect_display` 必须在启动浏览器前报配置错误（配置错误路径，退出码 2）。
- 运行产物沿用现有诊断包，不新增截图或基线文件。
- 版本从 `2.1.0` 升到 `2.2.0`，用 `scripts/bump_version.py`，与该功能最后一个运行时提交放在同一个提交里；推送前询问使用者。

## Review Focus

1. 隐藏元素里的文字不能算「已显示」（`display:none` / `visibility:hidden`）——Task 1 的 `test_expect_display_reports_hidden_value`。
2. 容器外出现同名文字不能让容器内缺失字段通过——Task 1 的 `test_expect_display_ignores_text_outside_container`。
3. 可滚动容器（`overflow:auto`）内容超出不能误报截断——Task 1 的 `test_expect_display_does_not_flag_scrollable_overflow`。
4. 容器异步出现时必须轮询等待，不能立即失败——Task 1 的 `test_expect_display_waits_for_late_container`。
5. 问题多、文本长时输出不能膨胀：最多 50 条、文本截断到 80 字——Task 1 的 `test_expect_display_caps_problem_count_and_text`。

---

### Task 1: 检测模块与流程接入

**Files:**
- Create: `runtime/browser/display.py`
- Create: `tests/browser_fixture/display.html`
- Modify: `runtime/browser/flow.py:19`（导入）、`runtime/browser/flow.py:398`（`expect_count` 分支之后）
- Modify: `tests/test_browser_flow.py`（文件末尾追加）

**Interfaces:**
- Consumes: `runtime.browser.locator.find`、`runtime.browser.flow.StepAssertion`、`apiwatch.ApiWatch.check`。
- Produces:
  - `runtime/browser/display.py` 中的 `check_display(page, spec: dict, aliases: dict[str, Any], timeout_ms: int, watch: ApiWatch | None = None) -> None`，失败时抛 `StepAssertion`，`detail` 含 `display_problems`（列表）和 `scan_limited`（布尔）。
  - 问题记录固定键：`kind`（`missing_field` / `empty_value` / `truncated`）、`field`、`text`、`tag`、`testid`、`class`、`reason`，无值一律 `None`。
  - `flow.py` 的 `_apply_expects` 支持 `expect_display`。
  - 供 Task 3 使用的 `detail.display_problems` 结构。

- [ ] **Step 1: 创建夹具 `tests/browser_fixture/display.html`**

```html
<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>显示检查夹具</title>
<style>
  .ellipsis { display:inline-block; width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; vertical-align:bottom; }
  .clip-ancestor { display:inline-block; width:80px; overflow:hidden; white-space:nowrap; vertical-align:bottom; }
  .clip-ancestor b { display:inline-block; width:200px; font-weight:normal; }
  .clamp { display:-webkit-box; -webkit-line-clamp:1; -webkit-box-orient:vertical; overflow:hidden; width:80px; }
  .scroll { display:inline-block; width:80px; overflow:auto; white-space:nowrap; vertical-align:bottom; }
  .hidden { visibility:hidden; }
</style>
</head>
<body>
  <div data-testid="ok">
    <span>委托单号</span><span>WO001</span>
    <span>客户名称</span><span>上海某某公司</span>
  </div>

  <div data-testid="missing"><span>委托单号</span><span>WO001</span></div>

  <div data-testid="empty">
    <span>委托单号</span><span>WO001</span>
    <span>客户名称</span><span></span>
  </div>

  <div data-testid="hidden-value">
    <span>客户名称</span><span class="hidden">上海某某公司</span>
  </div>

  <div data-testid="ellipsis">
    <span>收货地址</span><span class="ellipsis">上海市浦东新区某某路100号</span>
  </div>

  <div data-testid="ancestor">
    <span>备注</span><span class="clip-ancestor"><b>这是一段很长很长的备注内容</b></span>
  </div>

  <div data-testid="clamp">
    <span>描述</span><div class="clamp">第一行内容很长很长很长很长很长第二行内容</div>
  </div>

  <div data-testid="scroll">
    <span>货物清单</span><span class="scroll">很长很长的内容需要横向滚动查看以确认不被误报</span>
  </div>

  <div data-testid="allow">
    <span>备注</span><span class="ellipsis tag">这是一段允许截断的备注内容</span>
  </div>

  <div data-testid="allow-text">
    <span>备注</span><span class="ellipsis">这是允许备注截断的内容</span>
  </div>

  <div data-testid="mixed">
    <span>委托单号</span><span>WO001</span>
    <span class="ellipsis">收货地址内容很长很长很长很长很长</span>
  </div>

  <div data-testid="outside"><span>委托单号</span><span>WO001</span></div>
  <div data-testid="outside-extra"><span>客户名称</span><span>上海某某公司</span></div>

  <div data-testid="late"></div>
  <div data-testid="many"></div>
  <script>
    setTimeout(() => {
      document.querySelector('[data-testid="late"]').innerHTML =
        '<span>委托单号</span><span>WO001</span>';
    }, 300);
    const many = document.querySelector('[data-testid="many"]');
    for (let i = 0; i < 60; i++) {
      const s = document.createElement('span');
      s.className = 'ellipsis';
      s.textContent = '很长很长的内容第' + i + '段需要被裁切';
      many.appendChild(s);
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: 在 `tests/test_browser_flow.py` 末尾追加失败测试**

```python
def display_flow(fixture_url, case, fields=None, *, timeout=800, **display):
    spec = {"locator": {"testid": case}, **display}
    if fields is not None:
        spec["fields"] = fields
    return make_flow(
        {"name": "打开", "goto": fixture_url + "/display.html"},
        {"name": "显示检查", "expect_display": spec, "timeout": timeout},
    )


def test_expect_display_passes_when_fields_present(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "ok", ["委托单号", {"label": "客户名称", "value": "上海某某公司"}])
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_reports_missing_field(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "missing", ["客户名称"]))
    assert result.result == "fail"
    problems = result.failure.detail["display_problems"]
    assert [p["kind"] for p in problems] == ["missing_field"]
    assert problems[0]["field"] == "客户名称"
    assert "缺少字段 客户名称" in result.failure.message


def test_expect_display_reports_empty_value(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "empty", [{"label": "客户名称", "value": "上海某某公司"}]))
    assert result.result == "fail"
    assert result.failure.detail["display_problems"][0]["kind"] == "empty_value"


def test_expect_display_reports_hidden_value(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "hidden-value", [{"label": "客户名称", "value": "上海某某公司"}]))
    problem = result.failure.detail["display_problems"][0]
    assert problem["kind"] == "empty_value" and "不可见" in problem["reason"]


def test_expect_display_reports_truncated_declared_value(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "ellipsis",
                        [{"label": "收货地址", "value": "上海市浦东新区某某路100号"}], scan=False)
    problem = run(page, tmp_path, flow).failure.detail["display_problems"][0]
    assert problem["kind"] == "truncated" and problem["field"] == "收货地址"


def test_expect_display_scan_finds_unlisted_truncation(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "ellipsis", scan=True))
    problem = result.failure.detail["display_problems"][0]
    assert problem["kind"] == "truncated" and problem["field"] is None


def test_expect_display_reports_ancestor_clip(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "ancestor", scan=True))
    assert any("祖先" in p["reason"] for p in result.failure.detail["display_problems"])


def test_expect_display_reports_line_clamp(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "clamp", scan=True))
    assert "line-clamp" in result.failure.detail["display_problems"][0]["reason"]


def test_expect_display_allow_truncate_passes(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/display.html"},
        {"name": "文字放行", "expect_display": {
            "locator": {"testid": "allow-text"}, "allow_truncate": ["备注"]}, "timeout": 800},
        {"name": "选择器放行", "expect_display": {
            "locator": {"testid": "allow"}, "allow_truncate": [{"css": ".tag"}]}, "timeout": 800},
    )
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_scan_false_ignores_truncation(page, fixture_url, tmp_path):
    assert run(page, tmp_path, display_flow(fixture_url, "ellipsis", scan=False)).result == "pass"


def test_expect_display_does_not_flag_scrollable_overflow(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "scroll", ["货物清单"], scan=True)
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_waits_for_late_container(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "late", ["委托单号"], timeout=1500)
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_aggregates_problems(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "mixed", ["客户名称"]))
    kinds = {p["kind"] for p in result.failure.detail["display_problems"]}
    assert kinds == {"missing_field", "truncated"}
    assert "缺少字段 客户名称" in result.failure.message and "裁切" in result.failure.message


def test_expect_display_ignores_text_outside_container(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "outside", ["客户名称"]))
    assert result.failure.detail["display_problems"][0]["kind"] == "missing_field"


def test_expect_display_caps_problem_count_and_text(page, fixture_url, tmp_path):
    result = run(page, tmp_path, display_flow(fixture_url, "many", scan=True, timeout=1500))
    problems = result.failure.detail["display_problems"]
    assert len(problems) == 50
    assert all(len(p["text"] or "") <= 80 for p in problems)
    assert "50" in result.failure.message
```

- [ ] **Step 3: 运行新测试确认失败**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_flow.py -q -k "missing_field or empty_value"`
Expected: FAIL —— 目前 `expect_display` 没有实现，流程直接通过，失败断言不成立。

- [ ] **Step 4: 实现 `runtime/browser/display.py`**

模块结构：

```python
"""页面显示检查：字段完整性与截断扫描。"""

from __future__ import annotations

import time
from typing import Any

from .apiwatch import ApiWatch
from .locator import find

DISPLAY_JS = r"""..."""

def _summarize(problems: list[dict], scan_limited: bool) -> str: ...

def check_display(page: Any, spec: dict, aliases: dict[str, Any],
                  timeout_ms: int, watch: ApiWatch | None = None) -> None: ...
```

`DISPLAY_JS` 写成 `(container, args) => {...}`，返回 `{problems, scan_limited, text_elements}`，实现规则：

- `args` 为 `{"fields": [...], "scan": bool, "allow_truncate": [...]}`，由 Python 传入。
- 可见判定：元素矩形宽高均大于 0，且 `display != 'none'`、`visibility != 'hidden'`（不看 opacity）。
- 文本元素：容器自身及后代中，标签不属于 `SCRIPT/STYLE/NOSCRIPT/TEMPLATE/SVG/CANVAS/IMG/INPUT/TEXTAREA/SELECT/OPTION/BR/HR`、可见、且至少有一个非空白直接文本节点的元素；最多取前 5000 个，超出置 `scan_limited: true`。
- `textOf(el)`：`innerText` 把连续空白折叠为单个空格并 trim；描述里的 `text` 截到 80 字。
- 字段核对：字符串字段和 `{label}` 用「某个文本元素的 `textOf` 包含该文字」判定；找不到时用 `container.textContent`（折叠空白）区分「存在但不可见」和「容器内未找到该文字」；`{label, value}` 的 `value` 非空时同样匹配，找不到记 `empty_value`，值在 DOM 但不可见时 `reason` 写「存在但不可见」。
- 截断判定（`clipped(el)` 返回原因列表）：`overflow-x/y` 为 `hidden`/`clip` 且 `scrollWidth > clientWidth + 1` / `scrollHeight > clientHeight + 1`；`webkitLineClamp != 'none'` 且内容高度超出；祖先（直到容器含容器）`overflow-x/y` 为 `hidden`/`clip` 且元素矩形超出祖先可视矩形 1px 以上，原因写「被祖先 <tag>.<class> 裁切」。
- `overflow: auto/scroll` 不参与截断判定。
- `allow_truncate`：字符串按元素文本包含匹配，`{css}` 用 `el.matches(css)`；命中即跳过该元素的扫描问题。
- 字段核对命中的元素若被裁切，记 `truncated` 并带 `field`；扫描发现的问题 `field` 为 `None`。同一元素只报一次（用 `Set` 记录）。
- 问题条数最多 50；`kind`、`field`、`text`、`tag`、`testid`、`class`、`reason` 七个键始终存在，无值为 `None`。

`check_display` 逻辑：

- 函数内 `from .flow import StepAssertion`（避免循环导入）。
- `locator = find(page, spec["locator"], aliases)` 放在轮询外，多命中/非法定位器立即按现有错误抛出。
- 截止时间 `time.monotonic() + timeout_ms / 1000`；循环间隔 `0.1` 秒：
  - `locator.is_visible()` 为真时执行 `locator.evaluate(DISPLAY_JS, args)`；`TargetClosedError` 立即上抛，其他异常忽略并继续轮询。
  - 结果 `problems` 为空立即返回；否则记下本轮结果（`problems`、`scan_limited`）。
  - 每轮调用 `watch.check()`（`watch` 非空时）。
- 超时后：若从未拿到结果，合成一条 `{"kind": "missing_field", "field": None, "text": None, "tag": None, "testid": None, "class": None, "reason": "容器未出现或不可见"}`。
- 抛 `StepAssertion(_summarize(problems, scan_limited), "字段齐全且内容未被裁切", f"{len(problems)} 个问题", {"display_problems": problems, "scan_limited": scan_limited})`。
- `_summarize` 按 spec 第 5.4 节生成：`显示检查未通过：` 起头，分别拼「缺少字段 a、b…」「值为空 a、b…」「N 处内容被裁切（a、b…）」，每类最多展开 3 个名字；`scan_limited` 为真时追加「扫描已达上限」。

- [ ] **Step 5: 在 `flow.py` 接入断言**

导入区加 `from .display import check_display`。在 `_apply_expects` 的 `expect_count` 分支之后加：

```python
    if "expect_display" in step:
        check_display(page, step["expect_display"], aliases, timeout_ms, watch)
```

- [ ] **Step 6: 运行显示检查测试**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_flow.py -q -k expect_display`
Expected: PASS（全部）

- [ ] **Step 7: 运行全量测试**

Run: `".venv/Scripts/python.exe" -m pytest tests -q`
Expected: 全部通过；没有系统 Chrome 时浏览器用例按现有逻辑 skip。

- [ ] **Step 8: 提交**

```bash
git add runtime/browser/display.py runtime/browser/flow.py tests/browser_fixture/display.html tests/test_browser_flow.py
git commit -m "feat: 浏览器流程支持显示检查断言"
```

---

### Task 2: 配置结构校验

**Files:**
- Modify: `runtime/browser/config.py:13-15`（导入 `LocatorError`、`parse_locator`）、`:80` 附近（新增常量）、`:149-154`（`_validate_step` 内调用）
- Modify: `tests/test_browser_config.py`（文件末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `expect_display` 结构（`locator`/`fields`/`scan`/`allow_truncate`）。
- Produces: `_validate_display(spec: Any, where: str) -> None`，非法结构抛 `BrowserConfigError`。

- [ ] **Step 1: 在 `tests/test_browser_config.py` 末尾追加失败测试**

```python
def add_step(browser_project, yaml_step: str):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(path.read_text(encoding="utf-8") + yaml_step, encoding="utf-8")


def test_expect_display_valid_spec_loads(browser_project):
    add_step(browser_project, """  - name: 显示检查
    expect_display:
      locator: {testid: order-detail}
      fields:
        - 委托单号
        - {label: 客户名称, value: "${order_no}"}
      scan: false
      allow_truncate: [备注, {css: ".tag"}]
""")
    flow = load_flow("demo", "smoke")
    assert flow.steps[-1]["expect_display"]["locator"] == {"testid": "order-detail"}


def test_expect_display_locator_only_is_valid(browser_project):
    add_step(browser_project, "  - name: 扫描\n    expect_display:\n      locator: {testid: x}\n")
    flow = load_flow("demo", "smoke")
    assert "expect_display" in flow.steps[-1]


@pytest.mark.parametrize("body, match", [
    ("fields: [客户名称]", "locator"),
    ("locator: {testid: x}\n      unknown: 1", "unknown"),
    ("locator: {testid: x}\n      fields: ['']", "非空"),
    ("locator: {testid: x}\n      fields: [{value: 1}]", "label"),
    ("locator: {testid: x}\n      scan: false", "fields"),
    ("locator: {testid: x}\n      allow_truncate: [{role: button}]", "allow_truncate"),
    ("locator: {testid: x}\n      scan: 'yes'", "scan"),
])
def test_expect_display_rejects_invalid_spec(browser_project, body, match):
    add_step(browser_project, "  - name: 显示检查\n    expect_display:\n      " + body + "\n")
    with pytest.raises(BrowserConfigError, match=match):
        load_flow("demo", "smoke")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_config.py -q -k expect_display`
Expected: FAIL —— 非法结构目前能被 `load_flow` 接受（`expect_*` 键自动放行）。

- [ ] **Step 3: 实现校验**

`runtime/browser/config.py` 导入区增加 `from .locator import LocatorError, parse_locator`；常量区增加：

```python
_DISPLAY_FIELDS = {"locator", "fields", "scan", "allow_truncate"}
_DISPLAY_FIELD_FIELDS = {"label", "value"}
_ALLOW_TRUNCATE_FIELDS = {"css"}
```

新增函数，规则：

- `spec` 必须是映射，未知键报错（`_check_keys`）。
- `locator` 必填，用 `parse_locator` 校验，捕获 `LocatorError` 转成 `BrowserConfigError`，消息含 `expect_display.locator`。
- `fields` 可为空列表；每项是非空字符串，或映射：只允许 `label`/`value`，`label` 必须非空字符串，`value` 存在时必须是字符串。
- `scan` 默认 `True`，必须是布尔值。
- `allow_truncate` 每项是非空字符串或 `{css: "<非空字符串>"}`，其他键报错。
- `fields` 缺失/为空且 `scan` 显式为 `False` 时报错，消息含「fields」。
- 所有错误消息带 `where` 前缀，便于定位步骤。

在 `_validate_step` 的 `allow_api_error` 校验之后加入：

```python
    if "expect_display" in step:
        _validate_display(step["expect_display"], where)
```

- [ ] **Step 4: 运行配置测试**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_config.py -q`
Expected: PASS

- [ ] **Step 5: 运行全量测试**

Run: `".venv/Scripts/python.exe" -m pytest tests -q`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add runtime/browser/config.py tests/test_browser_config.py
git commit -m "feat: 校验显示检查断言配置"
```

---

### Task 3: 诊断输出与升版本

**Files:**
- Modify: `runtime/browser/diagnose.py:127-149`（`_diagnosis` 增加「显示问题」与建议）
- Modify: `tests/test_browser_report.py`（文件末尾追加）
- Modify: `tests/test_browser_cli.py`（文件末尾追加端到端验收）
- Modify: `.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`.cursor-plugin/plugin.json`（由脚本写入）

**Interfaces:**
- Consumes: Task 1 的 `detail.display_problems`（七个键）与 `detail.scan_limited`。
- Produces: `_display_line(problem: dict) -> str`；`diagnosis.md` 的「## 显示问题」一节。

- [ ] **Step 1: 在 `tests/test_browser_report.py` 末尾追加失败测试**

```python
def test_diagnosis_lists_display_problems(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    flow = FlowDef("smoke", "", "dev", {}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    result = failed_result(flow.path)
    result.failure.detail = {
        "display_problems": [
            {"kind": "missing_field", "field": "客户名称", "text": None, "tag": "div",
             "testid": "order-detail", "class": None, "reason": "容器内未找到该文字"},
            {"kind": "truncated", "field": None, "text": "上海市浦东新区", "tag": "td",
             "testid": None, "class": "el-table__cell", "reason": "scrollWidth 320 > clientWidth 120"},
        ],
        "scan_limited": False,
    }
    out = capture(page, "demo", flow, result, PageCollector())
    text = (out / "diagnosis.md").read_text(encoding="utf-8")
    assert "## 显示问题" in text
    assert "客户名称" in text and "scrollWidth 320 > clientWidth 120" in text
    assert "allow_truncate" in text
```

在 `tests/test_browser_cli.py` 末尾追加端到端验收（真实 Chrome；`browser_context` 仅用于没有 Chrome 时跳过）：

```python
def test_cli_run_writes_display_problems_to_diagnosis(browser_project, fixture_url, browser_context, capsys):
    from runtime.config import data_home

    (browser_project / "browser" / "browser.yaml").write_text(
        "version: 1\nproject: demo\nenvs:\n  dev:\n    base_url: ${WEB}\n"
        "defaults:\n  env: dev\n  timeout_ms: 1200\n  headless: true\n  resident: false\n",
        encoding="utf-8",
    )
    (browser_project / "browser" / "flows" / "display.yaml").write_text(
        """version: 1
flow: display
description: 显示检查
env: dev
steps:
  - name: 打开
    goto: ${BASE_URL}/display.html
  - name: 显示检查
    expect_display:
      locator: {testid: missing}
      fields: [客户名称]
    timeout: 800
""",
        encoding="utf-8",
    )
    (browser_project / ".env").write_text(f"WEB={fixture_url}\n", encoding="utf-8")

    assert cli.main(["run", "--project", "demo", "--flow", "display", "--env", "dev"]) == 1
    diagnosis = sorted((data_home() / "browser" / "artifacts").glob("*/diagnosis.md"))[-1]
    text = diagnosis.read_text(encoding="utf-8")
    assert "## 显示问题" in text and "客户名称" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_report.py tests/test_browser_cli.py -q -k "display"`
Expected: FAIL —— 诊断里没有「显示问题」。

- [ ] **Step 3: 实现诊断输出**

在 `_diagnosis` 里读取 `failure.detail` 的 `display_problems`（`failure` 为空时跳过），非空时在接口异常之后追加：

```markdown
## 显示问题
- [missing_field] 字段 客户名称 div[data-testid="order-detail"]：容器内未找到该文字
- [truncated] 文本 '上海市浦东新区' td.el-table__cell：scrollWidth 320 > clientWidth 120
```

- 新增 `_display_line(problem: dict) -> str`：kind 放方括号；有 `field` 时不重复打印 `text`；元素描述优先 `tag[data-testid="..."]`，否则 `tag.class`（类名空格换成点），再否则 `tag`；末尾拼 `reason`。`text` 用 `!r` 形式，避免与字段名混淆。
- 「建议」一节在接口异常建议之后追加：`- 显示问题：优先核对该字段是否漏渲染、容器/列宽是否不足；设计上允许省略的用 allow_truncate 放行。`

- [ ] **Step 4: 运行诊断与端到端测试**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_browser_report.py tests/test_browser_cli.py -q`
Expected: PASS（无系统 Chrome 时端到端用例按 `browser_context` 现有逻辑 skip）

- [ ] **Step 5: 升版本到 2.2.0**

Run: `".venv/Scripts/python.exe" scripts/bump_version.py 2.2.0`
Expected: 三个插件清单都更新为 `2.2.0`。

- [ ] **Step 6: 版本一致性与敏感信息检查**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_version_sync.py -q`
Expected: PASS

Run: `".venv/Scripts/python.exe" scripts/check_secrets.py`
Expected: 无敏感信息输出（退出码 0）。

- [ ] **Step 7: 运行全量测试**

Run: `".venv/Scripts/python.exe" -m pytest tests -q`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add runtime/browser/diagnose.py tests/test_browser_report.py tests/test_browser_cli.py .claude-plugin/plugin.json .codex-plugin/plugin.json .cursor-plugin/plugin.json
git commit -m "feat: 诊断输出显示问题并升版本至 2.2.0"
```

---

### Task 4: 文档与模板

**Files:**
- Modify: `skills/_references/browser-flow-contract.md:177-186`（第 6 节断言表）
- Modify: `skills/browser-test/SKILL.md:42-62`（执行）与 `:84-96`（失败处理）、`:98-104`（铁律）
- Modify: `skills/_references/browser-diagnosis.md:36-43`（判断提示）
- Modify: `skills/_TEMPLATE/browser-flow.example.yaml`（末尾追加步骤）
- Modify: `docs/usage.md`（第十三章浏览器测试）

**Interfaces:**
- Consumes: Task 1–3 的最终语法与诊断行为。
- Produces: 无代码接口；文档与模板与实现一致。

- [ ] **Step 1: 更新流程契约**

在 `browser-flow-contract.md` 第 6 节断言表增加一行：

```markdown
| `expect_display: {locator: ..., fields: [...], scan: true, allow_truncate: [...]}` | 容器内字段齐全且内容未被裁切，见 6.1 |
```

新增 `### 6.1 显示检查` 小节，内容为 spec 第 4.1 节的 YAML 示例，并写明：`fields` 支持纯文字与 `{label, value}`；`scan` 默认 `true`；`allow_truncate` 支持文字片段与 `{css}`；命中容器内隐藏元素不算显示；可滚动容器不算截断；失败时诊断包有「显示问题」清单。

- [ ] **Step 2: 更新技能说明**

`SKILL.md` 执行部分加一条：「关键详情页/列表页在数据稳定后加 `expect_display`，核对必须显示的字段并扫描截断；设计上允许省略的字段用 `allow_truncate` 放行。」失败处理表加一行：「诊断含『显示问题』→ 按清单判断是字段漏渲染、值为空还是列宽不足；确属设计性省略时用 `allow_truncate` 或 `scan: false`，不要放宽断言本身。」

- [ ] **Step 3: 更新诊断参考**

`browser-diagnosis.md` 的「判断提示」增加：`diagnosis.md` 有「显示问题」→ 先看 `failure.png` 和清单：字段漏渲染补前端，值为空查接口/渲染条件，被裁切调容器或列宽；允许省略的记为放行项并写入坑库。

- [ ] **Step 4: 更新流程模板**

在 `skills/_TEMPLATE/browser-flow.example.yaml` 末尾追加：

```yaml
  - name: 核对详情字段
    expect_display:
      locator: {testid: b2d-update-logistics-dialog}
      fields:
        - 物流方式
        - {label: 出库单号, value: "${order_no}"}
```

- [ ] **Step 5: 更新使用文档**

`docs/usage.md` 第十三章「日常使用」之后补一段：说明 `expect_display` 的作用、示例（复用 spec 第 4.1 节 YAML）、失败时诊断包里的「显示问题」一节，以及 `scan: false` / `allow_truncate` 的适用场景。

- [ ] **Step 6: 运行技能与全量测试**

Run: `".venv/Scripts/python.exe" -m pytest tests/test_skills.py -q`
Expected: PASS

Run: `".venv/Scripts/python.exe" -m pytest tests -q`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add skills/_references/browser-flow-contract.md skills/browser-test/SKILL.md skills/_references/browser-diagnosis.md skills/_TEMPLATE/browser-flow.example.yaml docs/usage.md
git commit -m "docs: 补充浏览器显示检查用法"
```
