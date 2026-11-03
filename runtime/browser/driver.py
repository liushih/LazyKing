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
    try:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel="chrome",
            headless=headless,
            viewport=None,
            accept_downloads=True,
        )
    except Exception as exc:
        playwright.stop()
        raise BrowserEnvError(
            f"无法启动 Chrome（profile: {profile}）：{exc}。"
            "请关闭占用该 profile 的 Chrome，或换 --profile。"
        ) from exc

    if tracing:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(15000)
    return BrowserSession(playwright=playwright, context=context, page=page)


def close(session: BrowserSession, trace_path: Path | None = None) -> None:
    try:
        if trace_path is not None:
            session.context.tracing.stop(path=str(trace_path))
    finally:
        try:
            session.context.close()
        finally:
            session.playwright.stop()


def check_login_success(page: Any, login: LoginConfig) -> bool:
    if login.success_url_path and urlparse(page.url).path != login.success_url_path:
        return False
    for key, pattern in login.success_localstorage.items():
        value = page.evaluate("key => localStorage.getItem(key)", key)
        if not value or not re.search(pattern, value):
            return False
    return True
