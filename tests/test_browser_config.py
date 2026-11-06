from pathlib import Path

import pytest

from runtime.browser.config import (
    BrowserConfigError,
    list_flows,
    load_browser_config,
    load_flow,
    profile_path,
    find_unresolved,
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


def test_find_unresolved_lists_undeclared_placeholders(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "  - name: 断言\n    expect_url: {contains: \"${MISSING_ONE}/${order_no}/${MISSING_TWO}\"}\n",
        encoding="utf-8",
    )
    cfg = load_browser_config("demo")
    flow = load_flow("demo", "smoke")
    variables = resolve_variables(cfg, flow, "dev", {"order_no": "A1"}, {})
    assert find_unresolved(flow, variables) == ["MISSING_ONE", "MISSING_TWO"]


def test_find_unresolved_tolerates_impl_provided_names(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "  - name: 调用\n    impl: scripts/x.py:go\n  - name: 用结果\n    expect_url: {contains: \"${from_impl}\"}\n",
        encoding="utf-8",
    )
    cfg = load_browser_config("demo")
    flow = load_flow("demo", "smoke")
    variables = resolve_variables(cfg, flow, "dev", {"order_no": "A1"}, {})
    assert find_unresolved(flow, variables) == []


def test_api_watch_defaults(browser_project):
    cfg = load_browser_config("demo")
    assert cfg.api_watch.enabled is True
    assert cfg.api_watch.ignore == ()
    assert cfg.api_watch.grace_ms == 1500


def test_api_watch_custom_settings(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  headless: false\n",
            "  headless: false\n  api_watch:\n    enabled: false\n    ignore: [/api/heartbeat]\n"
            "    success_codes: [1, \"OK\"]\n    grace_ms: 500\n",
        ),
        encoding="utf-8",
    )
    cfg = load_browser_config("demo")
    assert cfg.api_watch.enabled is False
    assert cfg.api_watch.ignore == ("/api/heartbeat",)
    assert cfg.api_watch.success_codes == ("1", "ok")
    assert cfg.api_watch.grace_ms == 500


def test_api_watch_unknown_field_raises(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  headless: false\n", "  headless: false\n  api_watch:\n    nope: 1\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(BrowserConfigError, match="nope"):
        load_browser_config("demo")


def test_api_watch_grace_must_be_non_negative_int(browser_project):
    path = browser_project / "browser" / "browser.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  headless: false\n", "  headless: false\n  api_watch:\n    grace_ms: -1\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(BrowserConfigError, match="grace_ms"):
        load_browser_config("demo")


def test_allow_api_error_accepts_bool_or_url_list(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "  - name: 允许\n    goto: ${BASE_URL}/x\n    allow_api_error: true\n"
        + "  - name: 部分允许\n    goto: ${BASE_URL}/y\n    allow_api_error: [/api/a]\n",
        encoding="utf-8",
    )
    flow = load_flow("demo", "smoke")
    assert flow.steps[1]["allow_api_error"] is True
    assert flow.steps[2]["allow_api_error"] == ["/api/a"]


def test_allow_api_error_rejects_other_types(browser_project):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "  - name: 非法\n    goto: ${BASE_URL}/x\n    allow_api_error: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(BrowserConfigError, match="allow_api_error"):
        load_flow("demo", "smoke")


def test_personal_yaml_supplies_login_username(browser_project):
    (browser_project / ".env").write_text(
        "WEB=http://localhost\nAPI=http://localhost/api\nPASS=secret\n",
        encoding="utf-8",
    )
    (browser_project / "personal.yaml").write_text(
        "USER: personal-admin\n", encoding="utf-8"
    )
    cfg = load_browser_config("demo")
    assert cfg.login.username == "personal-admin"


def test_missing_personal_guides_setup(browser_project):
    (browser_project / ".env").unlink()
    personal = browser_project / "personal.yaml"
    if personal.exists():
        personal.unlink()
    with pytest.raises(BrowserConfigError, match="project-setup"):
        load_browser_config("demo")


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
