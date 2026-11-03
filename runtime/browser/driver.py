"""Chrome 驱动与登录态检测。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import LoginConfig


class BrowserEnvError(Exception):
    pass


@dataclass
class BrowserSession:
    playwright: Any
    context: Any
    page: Any


def launch(headless: bool, profile: Path, *, tracing: bool = False) -> BrowserSession:
    from playwright.sync_api import sync_playwright

    profile = Path(profile)
    profile.parent.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    options: dict[str, Any] = {
        "channel": "chrome",
        "headless": headless,
        "accept_downloads": True,
    }
    if headless:
        options["viewport"] = {"width": 1280, "height": 720}
    else:
        # Python 里 viewport=None 等于没传（默认 1280x720）；不固定视口要用 no_viewport。
        # Playwright 默认带 --no-sandbox，Chrome 会在窗口顶部弹警告条；开启沙箱在部分环境会让 Chrome 启动即崩溃，
        # 所以保留默认沙箱行为，用 --test-type 只隐藏这条提示（仅用于本工具专用的自动化 profile）。
        options["no_viewport"] = True
        options["args"] = ["--start-maximized", "--test-type"]
    try:
        context = playwright.chromium.launch_persistent_context(str(profile), **options)
    except Exception as exc:
        playwright.stop()
        raise BrowserEnvError(
            f"无法启动 Chrome（profile: {profile}）：{exc}。"
            "请关闭占用该 profile 的 Chrome，或换 --profile。"
        ) from exc

    if tracing:
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
        except Exception:
            pass
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    return BrowserSession(playwright=playwright, context=context, page=page)


def close(session: BrowserSession, trace_path: Path | None = None) -> None:
    try:
        if trace_path is not None:
            try:
                session.context.tracing.stop(path=str(trace_path))
            except Exception:
                pass
    finally:
        try:
            session.context.close()
        finally:
            session.playwright.stop()


def check_login_success(page: Any, login: LoginConfig) -> bool:
    if login.success_localstorage:
        for key, pattern in login.success_localstorage.items():
            value = page.evaluate("key => localStorage.getItem(key)", key)
            if not value or not re.search(pattern, value):
                return False
        return True
    if login.success_url_path:
        return urlparse(page.url).path == login.success_url_path
    return True
