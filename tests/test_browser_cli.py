import subprocess
import sys
from pathlib import Path

from runtime.browser.config import BrowserConfig, EnvConfig, FlowDef, VarDef
from runtime.browser.flow import FlowResult, StepResult
from scripts import browser as cli


def fake_config():
    return BrowserConfig(
        project="demo",
        envs={"dev": EnvConfig("dev", "http://localhost", {"api": "http://localhost/api"})},
        default_env="dev", timeout_ms=1000, headless=False, profile=None, login=None,
    )


def fake_flow():
    return FlowDef("smoke", "", "dev", {"order_no": VarDef(True, None, "")}, [], Path("smoke.yaml"))


def test_help_runs_outside_pytest(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "browser.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert out.returncode == 0, out.stderr


def test_list_prints_flows(browser_project, capsys):
    assert cli.main(["list", "--project", "demo"]) == 0
    assert "smoke" in capsys.readouterr().out


def test_missing_flow_returns_3(browser_project):
    assert cli.main(["run", "--project", "demo", "--flow", "nope"]) == 3


def test_config_error_returns_2(browser_project):
    (browser_project / "browser" / "browser.yaml").write_text("version: 1\n", encoding="utf-8")
    assert cli.main(["run", "--project", "demo", "--flow", "smoke"]) == 2


def test_doctor_missing_config_returns_2(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    assert cli.main(["doctor", "--project", "demo"]) == 2


class _Session:
    page = object()


class _Collector:
    def attach(self, page):
        pass


def test_run_success_writes_report_and_returns_0(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(cli, "resolve_project", lambda project: project)
    monkeypatch.setattr(cli, "load_browser_config", lambda project: fake_config())
    monkeypatch.setattr(cli, "load_flow", lambda project, flow: fake_flow())
    monkeypatch.setattr(cli, "launch", lambda headless, profile, tracing=False: _Session())
    monkeypatch.setattr(cli, "PageCollector", _Collector)
    monkeypatch.setattr(cli, "ensure_login", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli, "run_flow",
        lambda *args, **kwargs: FlowResult("smoke", "dev", "pass", "now", 1, "smoke.yaml", [StepResult("打开", "pass", 1)]),
    )
    monkeypatch.setattr(cli, "write_report", lambda project, result: calls.setdefault("report", Path("report.json")))
    monkeypatch.setattr(cli, "close", lambda *args, **kwargs: None)
    assert cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1"]) == 0
    assert "report" in calls


def test_run_failure_captures_diagnostics_and_returns_1(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(cli, "resolve_project", lambda project: project)
    monkeypatch.setattr(cli, "load_browser_config", lambda project: fake_config())
    monkeypatch.setattr(cli, "load_flow", lambda project, flow: fake_flow())
    monkeypatch.setattr(cli, "launch", lambda headless, profile, tracing=False: _Session())
    monkeypatch.setattr(cli, "PageCollector", _Collector)
    monkeypatch.setattr(cli, "ensure_login", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli, "run_flow",
        lambda *args, **kwargs: FlowResult("smoke", "dev", "fail", "now", 1, "smoke.yaml", [StepResult("断言", "fail", 1, "x")]),
    )
    monkeypatch.setattr(cli, "capture", lambda *args, **kwargs: captured.setdefault("artifacts", Path("artifacts")))
    monkeypatch.setattr(cli, "write_report", lambda project, result: Path("report.json"))
    monkeypatch.setattr(cli, "close", lambda *args, **kwargs: None)
    assert cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1"]) == 1
    assert "artifacts" in captured


def test_undeclared_placeholder_is_config_error_before_launch(browser_project, monkeypatch):
    path = browser_project / "browser" / "flows" / "smoke.yaml"
    path.write_text(
        path.read_text(encoding="utf-8") + "  - name: 断言\n    expect_url: {contains: \"${NOT_DEFINED}\"}\n",
        encoding="utf-8",
    )
    launched = []
    monkeypatch.setattr(cli, "launch", lambda *args, **kwargs: launched.append(1))
    assert cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1"]) == 2
    assert launched == []


def test_trace_dir_failure_still_closes_browser(browser_project, monkeypatch, tmp_path):
    closed = []
    monkeypatch.setattr(cli, "launch", lambda headless, profile, tracing=False: _Session())
    monkeypatch.setattr(cli, "PageCollector", _Collector)
    monkeypatch.setattr(cli, "close", lambda *args, **kwargs: closed.append(1))
    monkeypatch.setattr(
        cli, "run_flow",
        lambda *args, **kwargs: FlowResult("smoke", "dev", "pass", "now", 1, "smoke.yaml", [StepResult("打开", "pass", 1)]),
    )
    monkeypatch.setattr(cli, "ensure_login", lambda *args, **kwargs: True)
    real_mkdir = Path.mkdir

    def failing_mkdir(self, *args, **kwargs):
        if "traces" in self.parts:
            raise OSError("denied")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)
    code = cli.main(["run", "--project", "demo", "--flow", "smoke", "--var", "order_no=A1", "--trace"])
    assert closed == [1]
    assert code == 0


def test_diagnose_shows_most_recent_across_flows(browser_project, tmp_path):
    import os

    root = tmp_path / "browser" / "artifacts"
    old = root / "zzz-flow-1"
    new = root / "aaa-flow-2"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "diagnosis.md").write_text("OLD", encoding="utf-8")
    (new / "diagnosis.md").write_text("NEW", encoding="utf-8")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    import io, contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert cli.main(["diagnose", "--project", "demo"]) == 0
    assert "NEW" in buf.getvalue() and "OLD" not in buf.getvalue()
