import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import update
from scripts.update import (
    Version,
    cache_is_fresh,
    is_newer,
    parse_version,
    read_cache,
    write_cache,
)


def test_parse_version_accepts_v_prefix():
    assert parse_version("v1.4.0") == Version(1, 4, 0)


def test_is_newer_compares_numerically():
    assert is_newer("1.9.0", "1.10.0") is True
    assert is_newer("1.10.0", "1.9.0") is False


def test_cache_round_trip(tmp_path):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    write_cache(tmp_path, "1.5.0", "abc1234", now)
    cache = read_cache(tmp_path)
    assert cache["latest_version"] == "1.5.0"
    assert cache_is_fresh(cache, now + timedelta(hours=1), 24) is True
    assert cache_is_fresh(cache, now + timedelta(hours=25), 24) is False


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return path


def _write_version(project, version="1.4.0", commit="aaa1111"):
    path = project / "data-tools"
    path.mkdir(parents=True, exist_ok=True)
    (path / "VERSION").write_text(
        f"version: {version}\nsource_commit: {commit}\n", encoding="utf-8"
    )


def _write_config(project, text):
    path = project / ".data-tools"
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.yaml").write_text(text, encoding="utf-8")


def _no_network(source):
    raise AssertionError("network")


def test_check_update_reports_new_tag(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "remote_versions", lambda source: [update.Version(1, 4, 0), update.Version(1, 5, 0)])
    monkeypatch.setattr(update, "remote_head", lambda source: None)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is True
    assert "v1.5.0" in result.message


def test_check_update_uses_fresh_cache_without_network(project, monkeypatch):
    _write_version(project)
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    update.write_cache(project, "1.5.0", None, now)
    monkeypatch.setattr(
        update, "remote_versions",
        lambda source: (_ for _ in ()).throw(AssertionError("network")),
    )
    result = update.check_update(project, source="https://example.com/repo.git", now=now)
    assert result.available is True


def test_check_update_swallows_network_error(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(
        update, "remote_versions",
        lambda source: (_ for _ in ()).throw(update.UpdateError("offline")),
    )
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False


def test_check_update_uses_commit_when_no_tags(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "remote_versions", lambda source: [])
    monkeypatch.setattr(update, "remote_head", lambda source: "bbb2222")
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is True
    assert "main@bbb2222" in result.message


def test_cli_check_returns_10_when_update_available(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(
        update, "check_update",
        lambda project_dir, source=None, now=None: update.CheckResult(
            True, "1.4.0", "1.5.0", "有新版本"
        ),
    )
    assert update.main(["--project-dir", str(project), "--check", "--quiet"]) == 10


# Carried ruling: check_update must stay total on missing/invalid local data,
# and settings from malformed config.yaml must be coerced, not crash or disable the cache.

def test_check_update_missing_version_is_unavailable(project, monkeypatch):
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False
    assert result.message
    assert not (Path(project) / "data-tools" / "VERSION").exists()


def test_check_update_invalid_local_version_is_unavailable(project, monkeypatch):
    _write_version(project, version="latest")
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False
    assert "version" in result.message


def test_check_update_quoted_interval_hours_uses_cache(project, monkeypatch):
    _write_version(project)
    _write_config(project, 'data_tools:\n  check_interval_hours: "24"\n')
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    update.write_cache(project, "1.5.0", None, now)
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git", now=now)
    assert result.available is True


def test_check_update_invalid_interval_hours_falls_back(project, monkeypatch):
    _write_version(project)
    _write_config(project, "data_tools:\n  check_interval_hours: not-a-number\n")
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    update.write_cache(project, "1.5.0", None, now - timedelta(hours=1))
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git", now=now)
    assert result.available is True


def test_check_update_coerces_quoted_update_check_false(project, monkeypatch):
    _write_version(project)
    _write_config(project, 'data_tools:\n  update_check: "false"\n')
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False
    assert "禁用" in result.message


def _completed(command, stdout, returncode=0, stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_remote_versions_parses_tags(monkeypatch):
    output = (
        "1111111\trefs/tags/v1.4.0\n"
        "2222222\trefs/tags/v1.5.0\n"
        "3333333\trefs/tags/not-a-version\n"
    )
    commands = []
    timeouts = []

    def fake_run(command, **kwargs):
        commands.append(command)
        timeouts.append(kwargs.get("timeout"))
        return _completed(command, output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert update.remote_versions("https://example.com/repo.git") == [
        Version(1, 4, 0),
        Version(1, 5, 0),
    ]
    assert commands[0][:2] == ["git", "ls-remote"]
    assert "--tags" in commands[0]
    assert "--refs" in commands[0]
    assert timeouts[0] == 5


def test_remote_head_returns_short_sha(monkeypatch):
    output = "abcdef1234567890abcdef1234567890abcdef12\trefs/heads/main\n"

    def fake_run(command, **kwargs):
        return _completed(command, output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert update.remote_head("https://example.com/repo.git") == "abcdef1"


def test_remote_versions_raises_update_error_on_failure(monkeypatch):
    def fake_run(command, **kwargs):
        return _completed(command, "", returncode=128, stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(update.UpdateError):
        update.remote_versions("https://example.com/repo.git")


# Review fixes: short-SHA prefix matching, retry after failure, totality and no credential leaks.

@pytest.mark.parametrize(
    "local_commit",
    ["abcdef1234567890abcdef1234567890abcdef12", "abcde"],
)
def test_check_update_matches_commit_by_prefix(project, monkeypatch, local_commit):
    _write_version(project, commit=local_commit)
    monkeypatch.setattr(update, "remote_versions", lambda source: [])
    monkeypatch.setattr(update, "remote_head", lambda source: "abcdef1")
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False


def test_check_update_unknown_local_commit_does_not_report_update(project, monkeypatch):
    _write_version(project, commit="unknown")
    monkeypatch.setattr(update, "remote_versions", lambda source: [])
    monkeypatch.setattr(update, "remote_head", lambda source: "bbb2222")
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False


def test_cache_is_fresh_uses_failure_cooldown(tmp_path):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    write_cache(tmp_path, None, None, now, failed=True)
    cache = read_cache(tmp_path)
    assert cache["failed"] is True
    assert cache_is_fresh(cache, now + timedelta(minutes=5), 24) is True
    assert cache_is_fresh(cache, now + timedelta(minutes=20), 24) is False


def test_check_update_retries_after_failure_cooldown(project, monkeypatch):
    _write_version(project)
    calls = []

    def failing(source):
        calls.append(source)
        raise update.UpdateError("offline")

    monkeypatch.setattr(update, "remote_versions", failing)
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    first = update.check_update(project, source="https://example.com/repo.git", now=now)
    second = update.check_update(
        project, source="https://example.com/repo.git", now=now + timedelta(minutes=5)
    )
    assert first.available is False
    assert second.available is False
    assert len(calls) == 1
    assert read_cache(project)["failed"] is True

    third = update.check_update(
        project, source="https://example.com/repo.git", now=now + timedelta(minutes=20)
    )
    assert third.available is False
    assert len(calls) == 2


def test_check_update_failure_cooldown_is_configurable(project, monkeypatch):
    _write_version(project)
    _write_config(project, "data_tools:\n  failure_cooldown_minutes: 2\n")
    calls = []

    def failing(source):
        calls.append(source)
        raise update.UpdateError("offline")

    monkeypatch.setattr(update, "remote_versions", failing)
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    update.check_update(project, source="https://example.com/repo.git", now=now)
    update.check_update(
        project, source="https://example.com/repo.git", now=now + timedelta(minutes=1)
    )
    assert len(calls) == 1
    update.check_update(
        project, source="https://example.com/repo.git", now=now + timedelta(minutes=3)
    )
    assert len(calls) == 2


def test_check_update_failure_message_does_not_leak_credentials(project, monkeypatch):
    _write_version(project)
    secret = "https://user:token@example.com/repo.git"  # noqa: secrets

    def failing(source):
        raise update.UpdateError(f"fatal: could not read from {secret}")

    monkeypatch.setattr(update, "remote_versions", failing)
    result = update.check_update(project, source=secret)
    assert result.available is False
    assert "token" not in result.message
    assert "user" not in result.message


def test_check_update_survives_cache_write_failure(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "remote_versions", lambda source: [Version(1, 5, 0)])

    def failing_write(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(update, "write_cache", failing_write)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is True


def test_check_update_survives_undecodable_local_files(project, monkeypatch):
    data_dir = project / "data-tools"
    data_dir.mkdir(parents=True)
    (data_dir / "VERSION").write_bytes(b"\xff\xfe\x00")
    config_dir = project / ".data-tools"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_bytes(b"\xff\xfe\x00")
    monkeypatch.setattr(update, "remote_versions", _no_network)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False


def test_apply_update_refuses_tracked_toolkit(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: True)
    with pytest.raises(update.UpdateError, match="git 跟踪"):
        update.apply_update(project, source="https://example.com/repo.git")


def test_apply_update_clones_and_syncs(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source="https://example.com/repo.git") == 0
    assert any("sync_project.py" in " ".join(call) for call in calls)


# Review fixes: dirty guard must fail closed, unknown commits force sync,
# clone must not prompt/hang, and the sync arguments must be exact.

def test_toolkit_is_tracked_skips_non_git_with_warning(project, capsys):
    assert update._toolkit_is_tracked(project) is False
    assert "不是 git 仓库" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["nonzero", "oserror", "timeout"])
def test_toolkit_is_tracked_fails_closed_when_git_errors(project, monkeypatch, failure):
    (project / ".git").mkdir()

    def fake_run(cmd, **kwargs):
        if failure == "oserror":
            raise OSError("boom")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(cmd, 128, "", "fatal")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    with pytest.raises(update.UpdateError, match="已中止"):
        update._toolkit_is_tracked(project)


def test_targets_excludes_codex(project):
    (project / "AGENTS.md").write_text("x", encoding="utf-8")
    assert "codex" not in update._targets(project)


@pytest.mark.parametrize(
    ("local_commit", "remote_commit"),
    [("unknown", "bbb2222"), ("aaa1111", "")],
)
def test_apply_update_syncs_when_commit_unknown(
    project, monkeypatch, local_commit, remote_commit
):
    _write_version(project, version="1.5.0", commit=local_commit)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, remote_commit, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source="https://example.com/repo.git") == 0
    assert any("sync_project.py" in " ".join(call) for call in calls)


def test_cli_apply_returns_1_on_update_error(project, monkeypatch, capsys):
    def failing_apply(project_dir, source=None):
        raise update.UpdateError("无法更新")

    monkeypatch.setattr(update, "apply_update", failing_apply)
    assert update.main(["--project-dir", str(project)]) == 1
    assert "无法更新" in capsys.readouterr().err


def test_apply_update_passes_project_id_targets_and_source_url(project, monkeypatch):
    _write_version(project)
    data_dir = project / ".data-tools"
    data_dir.mkdir(parents=True)
    (data_dir / "config.yaml").write_text("default_project: demo\n", encoding="utf-8")
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".cursor" / "rules").mkdir(parents=True)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source="https://example.com/repo.git") == 0

    sync_calls = [call for call in calls if "sync_project.py" in " ".join(call)]
    assert len(sync_calls) == 1
    assert sync_calls[0][0] == sys.executable
    assert Path(sync_calls[0][1]).name == "sync_project.py"
    assert sync_calls[0][2:] == [
        "--project-dir",
        str(project),
        "--project-id",
        "demo",
        "--targets",
        "claude,cursor",
        "--source-url",
        "https://example.com/repo.git",
    ]


def test_apply_update_clone_disables_prompts_and_times_out(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)
    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            captured.update(kwargs)
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source="https://example.com/repo.git") == 0
    assert captured["timeout"] == update.GIT_CLONE_TIMEOUT_SECONDS
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_apply_update_reports_clone_timeout(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    with pytest.raises(update.UpdateError, match="超时"):
        update.apply_update(project, source="https://example.com/repo.git")


def test_apply_update_rejects_undecodable_plugin_json(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_bytes(b"\xff\xfe\x00")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    with pytest.raises(update.UpdateError, match="plugin.json"):
        update.apply_update(project, source="https://example.com/repo.git")


# Review fixes: never persist credentials from the update source into VERSION or argv.

@pytest.mark.parametrize(
    "source",
    [
        "https://example.com/repo.git",
        "git@example.com:team/repo.git",
        "ssh://git@example.com/team/repo.git",
        "C:/repos/claudeTool",
    ],
)
def test_validate_source_allows_token_free_forms(source):
    assert update._validate_source(source) == source


@pytest.mark.parametrize(
    "source",
    [
        "https://user:token@example.com/repo.git",
        "https://token@example.com/repo.git",
        "ssh://user:secret@example.com/repo.git",
    ],
)
def test_apply_update_rejects_credential_source(project, monkeypatch, source):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)

    def fake_run(cmd, **kwargs):
        raise AssertionError("凭据源不应执行任何 git 命令")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    with pytest.raises(update.UpdateError, match="不能包含用户名或令牌"):
        update.apply_update(project, source=source)

    version_text = (project / "data-tools" / "VERSION").read_text(encoding="utf-8")
    assert "token" not in version_text
    assert "secret" not in version_text


def test_check_update_rejects_credential_source(project, monkeypatch):
    _write_version(project)
    called = []
    monkeypatch.setattr(
        update, "remote_versions", lambda source: called.append(source) or []
    )
    result = update.check_update(project, source="https://user:token@example.com/repo.git")
    assert result.available is False
    assert called == []


def test_apply_update_records_token_free_source(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_toolkit_is_tracked", lambda path: False)
    source = "https://example.com/repo.git"

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        elif "sync_project.py" in " ".join(cmd):
            recorded = cmd[cmd.index("--source-url") + 1]
            (project / "data-tools" / "VERSION").write_text(
                f"version: 1.5.0\nsource: {recorded}\n", encoding="utf-8"
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source=source) == 0
    version_text = (project / "data-tools" / "VERSION").read_text(encoding="utf-8")
    assert f"source: {source}" in version_text
