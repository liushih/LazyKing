import threading
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
    outcome = {}

    def second_launch():
        try:
            outcome["session"] = launch(headless=True, profile=profile)
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=second_launch)
    thread.start()
    thread.join(timeout=30)
    try:
        if "session" in outcome:
            close(outcome["session"])
            pytest.fail("同一 profile 的第二次启动意外成功")
        error = outcome.get("error")
        assert isinstance(error, BrowserEnvError)
        assert "profile" in str(error)
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


def test_local_storage_wins_when_page_stays_on_login(page, fixture_url):
    login = LoginConfig(
        url=fixture_url + "/login.html",
        username=None,
        password=None,
        steps=[],
        impl=None,
        success_url_path="/index.html",
        success_localstorage={"Admin-Token": r"token-\d+"},
    )
    page.goto(fixture_url + "/login.html")
    page.evaluate("localStorage.setItem('Admin-Token', 'token-123')")
    assert check_login_success(page, login) is True
