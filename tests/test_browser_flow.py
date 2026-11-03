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
