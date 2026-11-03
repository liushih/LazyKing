import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "browser_fixture"
DEFAULT_BROWSER_YAML = """
version: 1
project: demo
envs:
  dev:
    base_url: ${WEB}
    api: ${API}
defaults:
  env: dev
  timeout_ms: 12000
  headless: false
login:
  url: ${WEB}/login
  username: ${USER}
  password: ${PASS}
  steps:
    - fill: {placeholder: 手机号}
      value: ${username}
  success:
    url_path: /index
    localStorage:
      Admin-Token: ".+"
"""
DEFAULT_FLOW_YAML = """
version: 1
flow: smoke
description: 冒烟
env: dev
vars:
  order_no: {required: true, description: 单号}
steps:
  - name: 打开首页
    goto: ${BASE_URL}/index
"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def fixture_url():
    handler = functools.partial(_QuietHandler, directory=str(FIXTURE))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser_context(tmp_path_factory):
    sync_api = pytest.importorskip("playwright.sync_api")
    profile = tmp_path_factory.mktemp("chrome-profile")
    playwright = sync_api.sync_playwright().start()
    try:
        context = playwright.chromium.launch_persistent_context(
            str(profile), channel="chrome", headless=True, viewport=None
        )
    except Exception as exc:
        playwright.stop()
        pytest.skip(f"系统 Chrome 不可用：{exc}")
    yield context
    context.close()
    playwright.stop()


@pytest.fixture
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()


@pytest.fixture
def browser_project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    project = tmp_path / "projects" / "demo"
    (project / "browser" / "flows").mkdir(parents=True)
    (project / ".env").write_text(
        "WEB=http://localhost\nAPI=http://localhost/api\nUSER=admin\nPASS=secret\n",
        encoding="utf-8",
    )
    (project / "browser" / "browser.yaml").write_text(DEFAULT_BROWSER_YAML, encoding="utf-8")
    (project / "browser" / "flows" / "smoke.yaml").write_text(DEFAULT_FLOW_YAML, encoding="utf-8")
    return project
