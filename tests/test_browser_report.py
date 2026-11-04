import json
from pathlib import Path

from runtime.browser.config import FlowDef, VarDef
from runtime.browser.diagnose import PageCollector, capture, redact_headers
from runtime.browser.flow import FlowResult, StepFailure, StepResult
from runtime.browser.report import prune, write_report


def failed_result(flow_file: Path) -> FlowResult:
    return FlowResult(
        flow="smoke", env="dev", result="fail",
        started_at="2026-11-03T10:00:00+08:00", duration_ms=120,
        flow_file=str(flow_file),
        steps=[StepResult("打开", "pass", 50), StepResult("断言", "fail", 70, "文本不匹配")],
        failure=StepFailure(1, "断言", "文本不匹配", expected="不存在", actual="list-loaded", detail={}),
    )


def test_write_report_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    flow_file = tmp_path / "smoke.yaml"
    flow_file.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    for _ in range(3):
        write_report("demo", failed_result(flow_file))
    reports = sorted((tmp_path / "browser" / "reports").glob("*.json"))
    assert len(reports) == 3
    prune(tmp_path / "browser" / "reports", keep=2)
    assert len(list((tmp_path / "browser" / "reports").glob("*.json"))) == 2
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert data["failure"]["step_name"] == "断言"


def test_redact_headers():
    cleaned = redact_headers({"Authorization": "x", "Cookie": "y", "Accept": "json"})
    assert cleaned == {"Accept": "json"}


def test_capture_writes_diagnosis_package(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    collector = PageCollector()
    collector.attach(page)
    flow = FlowDef("smoke", "", "dev", {"order_no": VarDef(True, None, "")}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    result = failed_result(flow.path)
    out = capture(page, "demo", flow, result, collector)
    for name in ["diagnosis.md", "failure.png", "page.html", "requests.json", "console.log", "flow.snapshot.yaml", "run.log"]:
        assert (out / name).exists(), name
    text = (out / "diagnosis.md").read_text(encoding="utf-8")
    assert "断言" in text and "不存在" in text


def test_capture_survives_screenshot_failure(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    flow = FlowDef("smoke", "", "dev", {}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")

    def broken(*args, **kwargs):
        raise RuntimeError("page crashed")

    monkeypatch.setattr("runtime.browser.diagnose._screenshot", broken)
    out = capture(page, "demo", flow, failed_result(flow.path), PageCollector())
    assert (out / "diagnosis.md").exists()


def test_redact_url_hides_sensitive_query_values():
    from runtime.browser.diagnose import redact_url

    url = "http://h/dev-api/resource/sse?Authorization=Bearer%20abc.def&clientid=x&token=zzz&pageNum=1"
    cleaned = redact_url(url)
    assert "abc.def" not in cleaned and "zzz" not in cleaned
    assert "pageNum=1" in cleaned and "clientid=x" in cleaned
    assert redact_url("http://h/a/b") == "http://h/a/b"


def test_redact_headers_drops_custom_auth_headers():
    cleaned = redact_headers({"X-Auth-Token": "a", "Proxy-Authorization": "b", "X-Api-Key": "c", "Accept": "json"})
    assert cleaned == {"Accept": "json"}


def test_scrub_text_hides_tokens_in_free_text():
    from runtime.browser.diagnose import scrub_text

    jwt = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpbiI6InUifQ.abcDEF123_-xyz"
    text = f"goto http://h/x?token={jwt}&a=1 failed; header Bearer {jwt} and password=hunter22 ok"
    cleaned = scrub_text(text)
    assert jwt not in cleaned and "hunter22" not in cleaned
    assert "a=1" in cleaned and "failed" in cleaned


def test_capture_scrubs_page_url_and_error_text(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    secret = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpbiI6InUifQ.abcDEF123_-xyz"  # noqa: secrets 脱敏测试用的合成值，非真实凭据
    page.goto(fixture_url + "/index.html?token=" + secret)
    flow = FlowDef("smoke", "", "dev", {}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    result = failed_result(flow.path)
    result.steps[1].error = "navigating to http://h/x?token=" + secret + " failed"  # noqa: secrets 脱敏测试用的合成值，非真实凭据
    out = capture(page, "demo", flow, result, PageCollector())
    for name in ["diagnosis.md", "run.log", "page.html", "console.log"]:
        assert secret not in (out / name).read_text(encoding="utf-8"), name


def test_write_report_scrubs_error_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    secret = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpbiI6InUifQ.abcDEF123_-xyz"  # noqa: secrets 脱敏测试用的合成值，非真实凭据
    flow_file = tmp_path / "smoke.yaml"
    flow_file.write_text("x", encoding="utf-8")
    result = failed_result(flow_file)
    result.failure.message = "bad http://h/x?token=" + secret
    path = write_report("demo", result)
    assert secret not in path.read_text(encoding="utf-8")


def test_prune_removes_entries_older_than_max_age(tmp_path):
    import os
    import time

    old = tmp_path / "old"
    old.mkdir()
    stamp = time.time() - 8 * 86400
    os.utime(old, (stamp, stamp))
    new = tmp_path / "new"
    new.mkdir()

    prune(tmp_path, keep=10, max_age=7 * 86400)

    assert not old.exists()
    assert new.exists()


def test_prune_orders_by_modified_time_not_name(tmp_path):
    import os

    older = tmp_path / "zzz-flow-1.json"
    newer = tmp_path / "aaa-flow-2.json"
    older.write_text("o", encoding="utf-8")
    newer.write_text("n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    prune(tmp_path, keep=1)
    assert [p.name for p in tmp_path.iterdir()] == ["aaa-flow-2.json"]


def test_latest_entry_uses_modified_time(tmp_path):
    import os

    from runtime.browser.report import latest_entry

    a = tmp_path / "aaa-flow-2"
    z = tmp_path / "zzz-flow-1"
    a.mkdir()
    z.mkdir()
    os.utime(z, (1000, 1000))
    os.utime(a, (2000, 2000))
    assert latest_entry(tmp_path).name == "aaa-flow-2"
    assert latest_entry(tmp_path / "missing") is None


def test_diagnosis_lists_api_errors(page, fixture_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    page.goto(fixture_url + "/index.html")
    flow = FlowDef("smoke", "", "dev", {}, [], tmp_path / "flow.yaml")
    flow.path.write_text("version: 1\nflow: smoke\nsteps: []\n", encoding="utf-8")
    result = failed_result(flow.path)
    result.failure.detail = {
        "api_errors": [{"method": "POST", "url": "http://x/api/save", "status": 500,
                        "reason": "HTTP 500", "body": '{"msg": "服务异常"}'}]
    }
    out = capture(page, "demo", flow, result, PageCollector())
    text = (out / "diagnosis.md").read_text(encoding="utf-8")
    assert "接口异常" in text and "POST http://x/api/save" in text and "服务异常" in text
