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
