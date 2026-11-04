"""Chrome 驱动与登录态检测。"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from contextlib import contextmanager
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
    resident: bool = False
    disconnected: bool = False


def find_chrome() -> str | None:
    local = os.environ.get("LOCALAPPDATA")
    candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe") if local else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


# ---------------------------------------------------------------- profile 缓存

# Chrome 可以随时重建的缓存目录；删除它们不影响登录态（Cookies、Local Storage 等）。
_PROFILE_CACHE_DIRS = (
    "GPUPersistentCache",
    "GrShaderCache",
    "ShaderCache",
    "GraphiteDawnCache",
    "DawnGraphiteCache",
    "component_crx_cache",
    "extensions_crx_cache",
    "Crashpad",
    "BrowserMetrics",
)
_BROWSER_CACHE_DIRS = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "Media Cache",
    "Application Cache",
)
_SERVICE_WORKER_CACHE_DIRS = ("CacheStorage", "ScriptCache")


def _path_size(path: Path) -> int:
    total = 0
    try:
        entries = list(path.rglob("*"))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            pass
    return total


def _browser_dirs(profile: Path) -> list[Path]:
    try:
        children = list(profile.iterdir())
    except OSError:
        return []
    return [
        child
        for child in children
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile "))
    ]


def clear_profile_cache(profile: Path) -> int:
    """删除 profile 里 Chrome 可重建的缓存，保留 Cookies、Local Storage 等登录态。

    调用方必须保证该 profile 的 Chrome 已经关闭。返回释放的字节数。
    """
    profile = Path(profile)
    targets = [profile / name for name in _PROFILE_CACHE_DIRS]
    for browser_dir in _browser_dirs(profile):
        targets.extend(browser_dir / name for name in _BROWSER_CACHE_DIRS)
        targets.extend(
            browser_dir / "Service Worker" / name for name in _SERVICE_WORKER_CACHE_DIRS
        )
    freed = 0
    for target in targets:
        if not target.exists():
            continue
        size = _path_size(target)
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            freed += size
        except OSError:
            pass
    return freed


def profile_in_use(profile: Path) -> bool:
    """该 profile 的常驻 Chrome 是否正在运行。"""
    state = _read_state(Path(profile))
    return bool(state and _ws_url(state["port"]))


# ---------------------------------------------------------------- 一次性启动

def launch(
    headless: bool,
    profile: Path,
    *,
    tracing: bool = False,
    resident: bool = False,
) -> BrowserSession:
    if resident:
        return launch_resident(profile, tracing=tracing)

    from playwright.sync_api import sync_playwright

    profile = Path(profile)
    profile.parent.mkdir(parents=True, exist_ok=True)
    # 同一个 profile 同时只能被一个 Chrome 占用；一次性启动前先让出常驻的那个。
    stop_resident(profile)
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

    session = BrowserSession(playwright=playwright, context=context, page=None)
    _start_tracing(context, tracing)
    session.page = context.pages[0] if context.pages else context.new_page()
    session.page.set_default_timeout(15000)
    return session


def _start_tracing(context: Any, tracing: bool) -> None:
    if not tracing:
        return
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    except Exception:
        pass


def close(session: BrowserSession, trace_path: Path | None = None) -> None:
    try:
        if trace_path is not None:
            try:
                session.context.tracing.stop(path=str(trace_path))
            except Exception:
                pass
    finally:
        if session.resident:
            # 常驻浏览器只关自己开的页面并断开连接，浏览器本身留着给下一次用。
            try:
                session.page.close()
            except Exception:
                pass
            finally:
                session.playwright.stop()
            return
        try:
            session.context.close()
        finally:
            session.playwright.stop()


def session_lost(session: Any) -> bool:
    """测试浏览器（或测试页面）是否已被手动关闭或崩溃。"""
    if getattr(session, "disconnected", False):
        return True
    return page_closed(getattr(session, "page", None))


def page_closed(page: Any) -> bool:
    try:
        return bool(page.is_closed())
    except Exception:
        return False


# ---------------------------------------------------------------- 常驻浏览器

_STARTUP_TIMEOUT = 20.0
_EXIT_GRACE = 5.0
_STOP_TIMEOUT = 5.0
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _state_path(profile: Path) -> Path:
    profile = Path(profile)
    return profile.with_name(profile.name + ".resident.json")


def _read_state(profile: Path) -> dict | None:
    try:
        data = json.loads(_state_path(profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("port"), int):
        return None
    return data


def _drop_state(profile: Path) -> None:
    try:
        _state_path(profile).unlink()
    except OSError:
        pass


def _ws_url(port: int, timeout: float = 1.0) -> str | None:
    """调试端口存活时返回 CDP websocket 地址，否则返回 None。绕开系统代理。"""
    try:
        with _NO_PROXY.open(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return None
    url = data.get("webSocketDebuggerUrl") if isinstance(data, dict) else None
    return url if isinstance(url, str) and url else None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _startup_lock(profile: Path, timeout: float = 30.0):
    """多个测试同时启动时，只允许一个去拉起常驻 Chrome。"""
    path = profile.with_name(profile.name + ".resident.lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 60:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise BrowserEnvError(f"等待常驻 Chrome 启动超时（锁文件：{path}）")
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _pid_on_port(port: int) -> int | None:
    """监听该端口的进程 pid（Windows 用 netstat）；查不到返回 None。"""
    if os.name != "nt":
        return None
    try:
        raw = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    # netstat 输出按系统本地编码，表头可能含非 ASCII；数据行是 ASCII，宽松解码即可。
    out = raw.decode("utf-8", errors="replace")
    needle = f"127.0.0.1:{port}"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] == needle and parts[3] == "LISTENING" and parts[4].isdigit():
            return int(parts[4])
    return None


def _spawn_chrome(profile: Path, port: int) -> subprocess.Popen:
    chrome = find_chrome()
    if not chrome:
        raise BrowserEnvError("未找到 Chrome，请先安装 Google Chrome")
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--headless=new",
        "--window-size=1280,720",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    base: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
        # 尽量脱离调用方的作业对象，否则调用方退出时会把常驻 Chrome 一起带走。
        try:
            return subprocess.Popen(args, creationflags=flags | 0x01000000, **base)
        except OSError:
            return subprocess.Popen(args, creationflags=flags, **base)
    return subprocess.Popen(args, start_new_session=True, **base)


def ensure_resident(profile: Path) -> str:
    """确保该 profile 的常驻 Chrome 在运行，返回 CDP websocket 地址。"""
    profile = Path(profile)
    profile.parent.mkdir(parents=True, exist_ok=True)
    with _startup_lock(profile):
        state = _read_state(profile)
        if state:
            ws = _ws_url(state["port"])
            if ws:
                return ws
            _drop_state(profile)
            # 上次的 Chrome 已经不在了，顺手清掉遗留缓存再启动。
            clear_profile_cache(profile)

        port = _free_port()
        proc = _spawn_chrome(profile, port)
        deadline = time.monotonic() + _STARTUP_TIMEOUT
        exited_at: float | None = None
        while time.monotonic() < deadline:
            ws = _ws_url(port)
            if ws:
                _state_path(profile).write_text(
                    json.dumps(
                        {"pid": _pid_on_port(port) or proc.pid, "port": port, "profile": str(profile)}
                    ),
                    encoding="utf-8",
                )
                return ws
            if proc.poll() is not None:
                # 启动进程退出不等于启动失败：Chrome 可能把自己交给另一个进程继续启动。
                # 宽限期内端口起来了就算成功；一直没起来，才说明 profile 被别的 Chrome 占着。
                exited_at = exited_at or time.monotonic()
                if time.monotonic() - exited_at > _EXIT_GRACE:
                    raise BrowserEnvError(
                        f"常驻 Chrome 启动失败（profile: {profile}）。"
                        "请关闭占用该 profile 的 Chrome，或换 --profile。"
                    )
            time.sleep(0.2)
        _kill(proc.pid)
        raise BrowserEnvError(f"常驻 Chrome 启动超时（profile: {profile}）")


def launch_resident(profile: Path, *, tracing: bool = False) -> BrowserSession:
    from playwright.sync_api import sync_playwright

    profile = Path(profile)
    last_error: Exception | None = None
    for _ in range(2):
        ws = ensure_resident(profile)
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.connect_over_cdp(ws)
        except Exception as exc:
            playwright.stop()
            last_error = exc
            state = _read_state(profile)
            if state and _ws_url(state["port"]):
                # 浏览器好好的，是连接本身出了问题：重拉没有用，直接报真实原因。
                break
            # 浏览器在检查之后刚好被关了：清掉状态，重新拉起一次。
            _drop_state(profile)
            continue

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        page.set_viewport_size({"width": 1280, "height": 720})
        page.set_default_timeout(15000)
        session = BrowserSession(playwright=playwright, context=context, page=page, resident=True)
        browser.on("disconnected", lambda *_: setattr(session, "disconnected", True))
        _start_tracing(context, tracing)
        return session
    raise BrowserEnvError(f"无法连接常驻 Chrome（profile: {profile}）：{last_error}")


def stop_resident(profile: Path) -> bool:
    """关闭该 profile 的常驻 Chrome。确实关掉了一个返回 True，本来就没有返回 False。"""
    profile = Path(profile)
    state = _read_state(profile)
    if not state:
        return False
    port, pid = state["port"], state.get("pid")
    was_running = False
    ws = _ws_url(port)
    if ws:
        was_running = True
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            try:
                browser = playwright.chromium.connect_over_cdp(ws)
                browser.new_browser_cdp_session().send("Browser.close")
            finally:
                playwright.stop()
        except Exception:
            pass
        deadline = time.monotonic() + _STOP_TIMEOUT
        while time.monotonic() < deadline and _ws_url(port, timeout=0.5):
            time.sleep(0.2)
        if _ws_url(port, timeout=0.5) and isinstance(pid, int):
            _kill(pid)
    _drop_state(profile)
    # 浏览器已关，缓存可以安全删除；登录态保留，下次打开仍是登录状态。
    clear_profile_cache(profile)
    return was_running


def resident_profiles(root: Path) -> list[Path]:
    """root 下所有留有常驻状态的 profile 路径。"""
    suffix = ".resident.json"
    return sorted(
        path.with_name(path.name[: -len(suffix)])
        for path in Path(root).glob(f"**/*{suffix}")
    )


def _kill(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.kill(pid, 15)
    except OSError:
        pass


# ---------------------------------------------------------------- 登录态

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
