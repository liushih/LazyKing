import pytest
import yaml

from runtime.jenkins.client import BuildStatus, JenkinsError, JobParam
from scripts.jenkins import main
from test_jenkins_modules import _commit, _git

FAKE = "fake-jenkins-token-123"  # noqa: secrets
BASE = "http://jenkins.example.com"


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.params = {
            "order-dev": [JobParam("BRANCH", "StringParameterDefinition", "main", [])],
            "order-test": [JobParam("BRANCH", "StringParameterDefinition", "main", [])],
            "pay-dev": [],
            "stock-dev": [JobParam("BRANCH", "StringParameterDefinition", "main", [])],
        }
        self.trigger_errors = {}
        self.results = {}
        self.queue = {}
        self.timeouts = []

    def job_params(self, job):
        self.calls.append(("job_params", job))
        return self.params[job]

    def trigger(self, job, params):
        self.calls.append(("trigger", job, params))
        if job in self.trigger_errors:
            raise self.trigger_errors[job]
        url = f"{BASE}/queue/item/{len(self.queue) + 1}/"
        self.queue[url] = (job, 57 + len(self.queue))
        return url

    def wait_for_build(self, queue_url, timeout_s, poll_s=2.0):
        self.calls.append(("wait_for_build", queue_url))
        self.timeouts.append(timeout_s)
        return self.queue[queue_url][1]

    def wait_finished(self, job, number, timeout_s, poll_s=5.0):
        self.calls.append(("wait_finished", job, number))
        result = self.results.get(job, "SUCCESS")
        return BuildStatus(number, False, result, f"{BASE}/job/{job}/{number}/")

    def console_tail(self, job, number, lines=50):
        return f"boom in {job}\nlast line of {job}"

    def triggered(self):
        return [c[1] for c in self.calls if c[0] == "trigger"]


@pytest.fixture
def fake():
    return _FakeClient()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    project = tmp_path / "projects" / "demo"
    project.mkdir(parents=True)
    (project / "jenkins.yaml").write_text(
        yaml.safe_dump({
            "jenkins": {"base_url": BASE, "user": "u", "token_key": "JENKINS_TOKEN"},
            "baseline": "main",
            "modules": {
                "order-service": {
                    "paths": ["order-service/"],
                    "jobs": {"dev": "order-dev", "test": "order-test"},
                    "params": {"BRANCH": "{branch}"},
                },
                "pay-service": {"paths": ["pay-service/"], "jobs": {"dev": "pay-dev"}},
                "stock-service": {
                    "paths": ["stock-service/"],
                    "jobs": {"dev": "stock-dev"},
                    "params": {"BRANCH": "{branch}"},
                },
            },
        }),
        encoding="utf-8",
    )
    (project / ".env").write_text(f"JENKINS_TOKEN={FAKE}\n", encoding="utf-8")
    return project


def _run(args, fake):
    return main(["--project", "demo", "build", *args], client_fn=lambda cfg, token: fake)


ALL = ["--module", "order-service", "--module", "pay-service", "--module", "stock-service"]


def test_dry_run_prints_plan_and_triggers_nothing(home, fake, capsys):
    assert _run(["--env", "dev", "--module", "order-service", "--branch", "feature/x", "--dry-run"], fake) == 0
    out = capsys.readouterr().out
    assert fake.triggered() == []
    assert "order-service → order-dev" in out
    assert "BRANCH=feature/x" in out


def test_preflight_missing_env_job_blocks_everything(home, fake, capsys):
    code = _run(["--env", "test", "--module", "order-service", "--module", "pay-service", "--branch", "b"], fake)
    out = capsys.readouterr().out
    assert code == 2
    assert fake.triggered() == []
    assert "pay-service" in out and "test" in out


def test_preflight_rejects_unknown_param(home, fake, capsys):
    fake.params["order-dev"] = [JobParam("OTHER", "StringParameterDefinition", "x", [])]
    assert _run(["--env", "dev", "--module", "order-service", "--branch", "b"], fake) == 2
    assert "BRANCH" in capsys.readouterr().out
    assert fake.triggered() == []


def test_preflight_rejects_missing_required_param(home, fake, capsys):
    fake.params["order-dev"] = [
        JobParam("BRANCH", "StringParameterDefinition", "main", []),
        JobParam("ENV_NAME", "StringParameterDefinition", None, []),
    ]
    assert _run(["--env", "dev", "--module", "order-service", "--branch", "b"], fake) == 2
    assert "ENV_NAME" in capsys.readouterr().out
    assert fake.triggered() == []


def test_job_without_params_triggers_with_none_and_declared_with_dict(home, fake):
    assert _run(["--env", "dev", "--module", "pay-service", "--branch", "b", "--no-wait"], fake) == 0
    assert ("trigger", "pay-dev", None) in fake.calls

    fake.params["pay-dev"] = [JobParam("X", "StringParameterDefinition", "1", [])]
    assert _run(["--env", "dev", "--module", "pay-service", "--branch", "b", "--no-wait"], fake) == 0
    assert ("trigger", "pay-dev", {}) in fake.calls


def test_default_triggers_all_in_order_then_reports(home, fake, capsys):
    fake.results["pay-dev"] = "FAILURE"
    code = _run(["--env", "dev", *ALL, "--branch", "b"], fake)
    out = capsys.readouterr().out
    assert code == 1
    assert fake.triggered() == ["order-dev", "pay-dev", "stock-dev"]
    assert "[SUCCESS] order-service → order-dev #57" in out
    assert "[FAILURE] pay-service → pay-dev #58" in out
    assert "last line of pay-dev" in out
    assert "last line of order-dev" not in out
    assert fake.timeouts[0] == 30 * 60
    assert FAKE not in out


def test_trigger_failure_does_not_stop_others(home, fake, capsys):
    fake.trigger_errors["order-dev"] = JenkinsError("当前账号无权访问任务 order-dev", "permission", "order-dev")
    code = _run(["--env", "dev", *ALL, "--branch", "b"], fake)
    out = capsys.readouterr().out
    assert code == 1
    assert fake.triggered() == ["order-dev", "pay-dev", "stock-dev"]
    assert "[permission] order-service → order-dev" in out
    assert "[SUCCESS] pay-service → pay-dev" in out


def test_sequential_stops_on_first_failure(home, fake, capsys):
    fake.results["pay-dev"] = "FAILURE"
    code = _run(["--env", "dev", *ALL, "--branch", "b", "--sequential"], fake)
    out = capsys.readouterr().out
    assert code == 1
    assert fake.triggered() == ["order-dev", "pay-dev"]
    assert "[未触发] stock-service" in out
    order = [c for c in fake.calls if c[0] in ("trigger", "wait_finished")]
    assert [c[0] for c in order] == ["trigger", "wait_finished", "trigger", "wait_finished"]


def test_no_wait_prints_queue_urls(home, fake, capsys):
    code = _run(["--env", "dev", "--module", "order-service", "--branch", "b", "--no-wait"], fake)
    out = capsys.readouterr().out
    assert code == 0
    assert f"{BASE}/queue/item/1/" in out
    assert not any(c[0] in ("wait_for_build", "wait_finished") for c in fake.calls)


def test_unknown_module_name_exits_2(home, fake, capsys):
    assert _run(["--env", "dev", "--module", "nope", "--branch", "b"], fake) == 2
    assert "nope" in capsys.readouterr().out


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README.md")
    return repo


def test_no_modules_selected_exits_2(home, tmp_path, fake, capsys):
    repo = _repo(tmp_path)
    assert _run(["--env", "dev", "--repo", str(repo)], fake) == 2
    assert "没有可构建的模块" in capsys.readouterr().out
    assert fake.triggered() == []


def test_build_infers_modules_and_branch_from_repo(home, tmp_path, fake, capsys):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "order-service/x.py")
    assert _run(["--env", "dev", "--repo", str(repo), "--dry-run"], fake) == 0
    out = capsys.readouterr().out
    assert "order-service → order-dev" in out
    assert "BRANCH=feat" in out
    assert "pay-service" not in out
