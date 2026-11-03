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


def test_close_survives_trace_stop_failure():
    from runtime.browser.driver import BrowserSession

    calls = []

    class Tracing:
        def stop(self, path):
            raise RuntimeError("trace stop failed")

    class Context:
        tracing = Tracing()

        def close(self):
            calls.append("context")

    class Playwright:
        def stop(self):
            calls.append("playwright")

    close(BrowserSession(Playwright(), Context(), object()), trace_path=Path("t.zip"))
    assert calls == ["context", "playwright"]


class _FakePage:
    def set_default_timeout(self, ms):
        pass


class _FakeContext:
    pages = [_FakePage()]


class _FakeChromium:
    def __init__(self):
        self.kwargs = None

    def launch_persistent_context(self, profile, **kwargs):
        self.kwargs = kwargs
        return _FakeContext()


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()

    def stop(self):
        pass


def _launch_with_fake(monkeypatch, tmp_path, headless):
    fake = _FakePlaywright()

    class _Starter:
        def start(self):
            return fake

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _Starter())
    launch(headless=headless, profile=tmp_path / "profile")
    return fake.chromium.kwargs


def test_headed_launch_uses_real_window_size_and_hides_unsupported_flag_banner(monkeypatch, tmp_path):
    kwargs = _launch_with_fake(monkeypatch, tmp_path, headless=False)
    assert kwargs["no_viewport"] is True
    assert "viewport" not in kwargs
    assert "--start-maximized" in kwargs["args"]
    assert "--test-type" in kwargs["args"]
    assert "chromium_sandbox" not in kwargs


def test_headless_launch_keeps_fixed_1280x720_viewport(monkeypatch, tmp_path):
    kwargs = _launch_with_fake(monkeypatch, tmp_path, headless=True)
    assert kwargs["viewport"] == {"width": 1280, "height": 720}
    assert "no_viewport" not in kwargs
