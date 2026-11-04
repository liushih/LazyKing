import io

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
        self.whoami_error = None
        self.jobs = {
            "a/order-dev": [JobParam("BRANCH", "StringParameterDefinition", "main", [])],
            "pay-dev": [JobParam("ENV", "ChoiceParameterDefinition", None, ["dev", "test"])],
        }
        self.statuses = {}

    def whoami(self):
        if self.whoami_error:
            raise self.whoami_error
        return "u"

    def list_jobs(self):
        return sorted(self.jobs)

    def job_params(self, job):
        return self.jobs[job]

    def build_status(self, job, number):
        return self.statuses[(job, number)]


@pytest.fixture
def fake():
    return _FakeClient()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    return tmp_path / "projects" / "demo"


def _configure(home, baseline="main"):
    (home / "jenkins.yaml").write_text(
        yaml.safe_dump({
            "jenkins": {"base_url": BASE, "user": "u", "token_key": "JENKINS_TOKEN"},
            "baseline": baseline,
            "modules": {"order-service": {
                "paths": ["order-service/"], "jobs": {"dev": "a/order-dev"},
            }},
        }),
        encoding="utf-8",
    )
    (home / ".env").write_text(f"JENKINS_TOKEN={FAKE}\n", encoding="utf-8")


def _run(args, fake, stdin=None):
    return main(["--project", "demo", *args], client_fn=lambda cfg, token: fake, stdin=stdin)


def test_setup_reads_token_from_stdin_and_never_prints_it(home, fake, capsys):
    code = _run(["setup", "--base-url", BASE, "--user", "u"], fake, stdin=io.StringIO(FAKE + "\n"))
    out = capsys.readouterr()
    assert code == 0
    assert f"JENKINS_TOKEN={FAKE}" in (home / ".env").read_text(encoding="utf-8")
    assert FAKE not in out.out + out.err
    assert "登录为 u" in out.out


def test_setup_verify_failure_keeps_config_and_exits_1(home, fake, capsys):
    fake.whoami_error = JenkinsError("账号或 token 无效", "auth")
    code = _run(["setup", "--base-url", BASE, "--user", "u"], fake, stdin=io.StringIO(FAKE))
    out = capsys.readouterr()
    assert code == 1
    assert (home / "jenkins.yaml").exists()
    assert "[auth]" in out.out
    assert FAKE not in out.out + out.err


def test_setup_empty_stdin_exits_2_and_writes_nothing(home, fake, capsys):
    code = _run(["setup", "--base-url", BASE, "--user", "u"], fake, stdin=io.StringIO("  \n"))
    assert code == 2
    assert not (home / "jenkins.yaml").exists()
    assert "token" in capsys.readouterr().out


def test_discover_lists_jobs_with_params_and_filter(home, fake, capsys):
    _configure(home)
    assert _run(["discover", "--filter", "ORDER"], fake) == 0
    out = capsys.readouterr().out
    assert "a/order-dev" in out
    assert "  - BRANCH (StringParameterDefinition) 默认=main" in out
    assert "pay-dev" not in out


def test_discover_marks_required_and_choices(home, fake, capsys):
    _configure(home)
    _run(["discover", "--filter", "pay"], fake)
    out = capsys.readouterr().out
    assert "  - ENV (ChoiceParameterDefinition) 默认=无 可选=dev,test" in out


def test_modules_reports_hits_and_unmapped(home, tmp_path, fake, capsys):
    _configure(home)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README.md")
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "order-service/x.py")
    _commit(repo, "docs/a.md")
    assert _run(["modules", "--repo", str(repo)], fake) == 0
    out = capsys.readouterr().out
    assert "feat" in out
    assert "order-service" in out
    assert "docs/a.md" in out
    assert "远端无该分支" in out


def test_modules_exit_1_when_no_hit(home, tmp_path, fake, capsys):
    _configure(home)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README.md")
    assert _run(["modules", "--repo", str(repo)], fake) == 1
    assert "无命中模块" in capsys.readouterr().out


def test_modules_bad_baseline_exits_1_without_traceback(home, tmp_path, fake, capsys):
    _configure(home, baseline="origin/nope")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README.md")
    assert _run(["modules", "--repo", str(repo)], fake) == 1
    assert "origin/nope" in capsys.readouterr().out


def test_status_prints_result(home, fake, capsys):
    _configure(home)
    fake.statuses[("a/order-dev", 57)] = BuildStatus(57, False, "SUCCESS", f"{BASE}/job/a/job/order-dev/57/")
    fake.statuses[("a/order-dev", 58)] = BuildStatus(58, False, "FAILURE", "http://j/58/")
    fake.statuses[("a/order-dev", 59)] = BuildStatus(59, True, None, "http://j/59/")
    assert _run(["status", "--job", "a/order-dev", "--number", "57"], fake) == 0
    assert "[SUCCESS] a/order-dev #57" in capsys.readouterr().out
    assert _run(["status", "--job", "a/order-dev", "--number", "58"], fake) == 1
    assert _run(["status", "--job", "a/order-dev", "--number", "59"], fake) == 0
    assert "[BUILDING]" in capsys.readouterr().out


def test_missing_config_exits_2(home, fake, capsys):
    assert _run(["discover"], fake) == 2
    assert "jenkins.yaml" in capsys.readouterr().out


def test_missing_token_exits_2_and_names_key_only(home, fake, capsys):
    _configure(home)
    (home / ".env").write_text("OTHER=secret-other-value\n", encoding="utf-8")
    assert _run(["discover"], fake) == 2
    out = capsys.readouterr().out
    assert "JENKINS_TOKEN" in out
    assert "secret-other-value" not in out


def test_modules_reports_uncommitted_files_separately(home, tmp_path, fake, capsys):
    _configure(home)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README.md")
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "order-service/x.py")
    (repo / "order-service" / "wip.py").write_text("x", encoding="utf-8")
    assert _run(["modules", "--repo", str(repo)], fake) == 0
    out = capsys.readouterr().out
    assert "未提交" in out and "order-service/wip.py" in out


def test_setup_placeholder_mode_writes_personal_and_env(home, fake, capsys):
    code = _run(
        ["setup", "--base-url", BASE, "--user", "liushihao"],
        fake,
        stdin=io.StringIO(FAKE),
    )
    assert code == 0
    assert "JENKINS_USER: liushihao" in (home / "personal.yaml").read_text(
        encoding="utf-8"
    )
    assert f"JENKINS_TOKEN={FAKE}" in (home / ".env").read_text(encoding="utf-8")
