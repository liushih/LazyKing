import os
import subprocess
from pathlib import Path

import pytest

from runtime.track_shared import TrackError, track_shared


def _git(repo, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _init(tmp_path: Path) -> Path:
    repo = tmp_path / "biz"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "config", "user.email", "t@x.com")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("biz", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _write(repo: Path, rel: str, text: str = "ok\n") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_stages_shareable_flow_without_force(tmp_path):
    repo = _init(tmp_path)
    rel = ".data-tools/projects/hexincloud/browser/flows/package-biz-tag-append.yaml"
    _write(repo, rel, "version: 1\n")

    result = track_shared(repo, [rel])

    assert result.staged == [rel]
    assert _git(repo, "diff", "--cached", "--name-only") == rel


def test_stages_adapter_example_and_impl(tmp_path):
    repo = _init(tmp_path)
    paths = [
        ".data-tools/projects/hexincloud/adapter.yaml",
        ".data-tools/projects/hexincloud/.env.example",
        ".data-tools/projects/hexincloud/scripts/chain.py",
        ".data-tools/templates/hexincloud/weekly.md",
    ]
    for rel in paths:
        _write(repo, rel)

    result = track_shared(repo, paths)

    assert result.staged == paths
    assert sorted(_git(repo, "diff", "--cached", "--name-only").splitlines()) == sorted(paths)


def test_rejects_private_and_runtime_artifacts(tmp_path):
    repo = _init(tmp_path)
    private = [
        ".data-tools/projects/hexincloud/.env",
        ".data-tools/projects/hexincloud/personal.yaml",
        ".data-tools/projects/hexincloud/ledger.csv",
        ".data-tools/projects/hexincloud/scripts/state.json",
        ".data-tools/projects/hexincloud/.token.json",
        ".data-tools/browser/reports/last.html",
    ]
    for rel in private:
        _write(repo, rel)

    with pytest.raises(TrackError):
        track_shared(repo, private)

    assert _git(repo, "diff", "--cached", "--name-only") == ""


def test_skips_gitignored_shareable_file(tmp_path):
    repo = _init(tmp_path)
    rel = ".data-tools/projects/hexincloud/browser/flows/local.yaml"
    _write(repo, rel)
    (repo / ".gitignore").write_text(".data-tools/projects/*/browser/flows/local.yaml\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "ignore local flow")

    result = track_shared(repo, [rel])

    assert result.staged == []
    assert result.ignored == [rel]
    assert rel not in _git(repo, "diff", "--cached", "--name-only").splitlines()


def test_reports_already_tracked_file_as_unchanged(tmp_path):
    repo = _init(tmp_path)
    rel = ".data-tools/projects/hexincloud/browser/browser.yaml"
    _write(repo, rel, "version: 1\n")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", "add browser")

    result = track_shared(repo, [rel])

    assert result.unchanged == [rel]
    assert result.staged == []


def test_rejects_path_outside_repo(tmp_path):
    repo = _init(tmp_path)
    outside = tmp_path / "outside.yaml"
    outside.write_text("nope", encoding="utf-8")

    with pytest.raises(TrackError):
        track_shared(repo, [str(outside)])
