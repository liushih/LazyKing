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
