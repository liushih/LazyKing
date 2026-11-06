import pytest

from pathlib import Path

from runtime.browser.config import BrowserConfig, EnvConfig, FlowDef, LoginConfig, VarDef
from runtime.browser.flow import FlowRunError, ensure_login, run_flow


class TargetClosedError(Exception):
    """与 Playwright 同名的替身：_wait_until 按类名识别。"""


def test_wait_until_stops_immediately_when_browser_is_closed():
    import time

    from runtime.browser.flow import _wait_until

    def predicate():
        raise TargetClosedError("Target page, context or browser has been closed")

    started = time.monotonic()
    with pytest.raises(TargetClosedError):
        _wait_until(predicate, timeout_ms=10000)
    assert time.monotonic() - started < 1


def test_wait_until_still_retries_ordinary_errors():
    from runtime.browser.flow import _wait_until

    calls = []

    def predicate():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("元素还没出现")
        return True

    assert _wait_until(predicate, timeout_ms=2000) is True
    assert len(calls) == 3


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


def test_use_row_waits_for_layout_to_settle_before_next_click(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/jitter.html"},
        {"name": "定位", "use_row": {"row_css": "#host", "text": "日志"}, "as": "row", "wait_visible": True},
        {"name": "点击", "click": {"in": "row", "role": "button", "name": "日志"}},
        {"name": "断言", "expect_text": {"locator": {"css": "#result"}, "equals": "clicked-after-settle"}},
    )
    result = run(page, tmp_path, flow, timeout_ms=3000)
    assert result.result == "pass", result.failure


def test_optional_step_is_skipped(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/index.html"},
        {"name": "不存在", "click": {"testid": "nope"}, "optional": True},
        {"name": "继续", "expect_visible": {"css": "table"}},
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


def test_expect_display_declared_value_uses_innermost_match(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "wrapped",
                        [{"label": "收货地址", "value": "上海市浦东新区某某路100号"}], scan=False)
    problem = run(page, tmp_path, flow).failure.detail["display_problems"][0]
    assert problem["kind"] == "truncated" and problem["field"] == "收货地址"


def test_expect_display_allow_truncate_covers_declared_fields(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "ellipsis",
                        [{"label": "收货地址", "value": "上海市浦东新区某某路100号"}],
                        scan=False, allow_truncate=["收货地址"])
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_caps_expected_value_text(page, fixture_url, tmp_path):
    value = "长" * 120
    result = run(page, tmp_path, display_flow(fixture_url, "long-value",
                                              [{"label": "客户名称", "value": value}]))
    problem = result.failure.detail["display_problems"][0]
    assert problem["kind"] == "empty_value" and len(problem["text"]) == 80


def test_expect_display_dedupes_same_element_truncation(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "same-element",
                        [{"label": "客户名称", "value": "上海某某公司很长很长的地址内容"}], scan=True)
    problems = run(page, tmp_path, flow).failure.detail["display_problems"]
    assert len(problems) == 1 and problems[0]["kind"] == "truncated"


def test_expect_display_normalizes_whitespace_in_fields(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "spaced",
                        [" 客户名称 ", {"label": "客户名称", "value": "上海\n某某公司"}])
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_ignores_whitespace_only_value(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "ok", [{"label": "客户名称", "value": "   "}])
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_ignores_clipping_outside_container(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "inner-text-body", ["这是一段容器自身的文字内容"], scan=False)
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_skips_svg_text(page, fixture_url, tmp_path):
    flow = display_flow(fixture_url, "svg-case", scan=True)
    assert run(page, tmp_path, flow).result == "pass"


def test_expect_display_scan_limited_only_when_scanning(page, fixture_url, tmp_path):
    flow = make_flow(
        {"name": "打开", "goto": fixture_url + "/display-huge.html"},
        {"name": "显示检查", "expect_display": {
            "locator": {"testid": "huge"}, "fields": ["不存在的字段"], "scan": False}, "timeout": 300},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "fail"
    assert "扫描已达上限" not in result.failure.message
