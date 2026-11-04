import os
import time
from pathlib import Path

from runtime.browser.driver import clear_profile_cache
from runtime.browser.report import ARTIFACT_KEEP, clean_all, cleanup


def _touch(path: Path, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    if age_days:
        _age(path, age_days)
    return path


def _age(path: Path, age_days: float) -> None:
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))


def test_cleanup_removes_stale_artifacts_probes_and_traces(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    old_artifact = _touch(tmp_path / "browser" / "artifacts" / "old" / "failure.png")
    _age(old_artifact.parent, 8)
    new_artifact = _touch(tmp_path / "browser" / "artifacts" / "new" / "failure.png")
    old_probe = _touch(tmp_path / "browser" / "probes" / "old" / "page.png")
    _age(old_probe.parent, 8)
    new_probe = _touch(tmp_path / "browser" / "probes" / "new" / "page.png")
    old_trace = _touch(tmp_path / "browser" / "traces" / "old.zip")
    _age(old_trace, 4)
    new_trace = _touch(tmp_path / "browser" / "traces" / "new.zip")

    counts = cleanup()

    assert not old_artifact.exists() and new_artifact.exists()
    assert not old_probe.exists() and new_probe.exists()
    assert not old_trace.exists() and new_trace.exists()
    assert counts["artifacts"] == 1
    assert counts["probes"] == 1
    assert counts["traces"] == 1


def test_cleanup_keeps_newest_artifacts_up_to_count(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    artifacts = tmp_path / "browser" / "artifacts"
    for index in range(ARTIFACT_KEEP + 3):
        entry = artifacts / f"pkg-{index}"
        entry.mkdir(parents=True)
        _age(entry, (ARTIFACT_KEEP + 3 - index) / (24 * 60))

    cleanup()

    remaining = sorted(path.name for path in artifacts.iterdir())
    assert len(remaining) == ARTIFACT_KEEP
    assert "pkg-0" not in remaining and f"pkg-{ARTIFACT_KEEP + 2}" in remaining


def test_clean_all_removes_fresh_artifacts_and_probes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    artifact = _touch(tmp_path / "browser" / "artifacts" / "pkg" / "failure.png")
    probe = _touch(tmp_path / "browser" / "probes" / "snap" / "page.png")
    trace = _touch(tmp_path / "browser" / "traces" / "run.zip")
    report = _touch(tmp_path / "browser" / "reports" / "smoke.json")

    counts = clean_all()

    assert not artifact.exists()
    assert not probe.exists()
    assert not trace.exists()
    assert report.exists()
    assert counts["artifacts"] == 1
    assert counts["probes"] == 1
    assert counts["traces"] == 1


def test_clear_profile_cache_keeps_login_state(tmp_path):
    profile = tmp_path / "profile"
    cookies = _touch(profile / "Default" / "Cookies")
    local_storage = _touch(profile / "Default" / "Local Storage" / "leveldb" / "000003.log")
    _touch(profile / "Default" / "Cache" / "data_0")
    _touch(profile / "Default" / "Code Cache" / "js" / "index")
    _touch(profile / "Default" / "Service Worker" / "CacheStorage" / "data")
    sw_database = _touch(profile / "Default" / "Service Worker" / "Database" / "db")
    _touch(profile / "GPUPersistentCache" / "GPUCache" / "data_0")

    freed = clear_profile_cache(profile)

    assert not (profile / "Default" / "Cache").exists()
    assert not (profile / "Default" / "Code Cache").exists()
    assert not (profile / "Default" / "Service Worker" / "CacheStorage").exists()
    assert sw_database.exists()
    assert not (profile / "GPUPersistentCache").exists()
    assert cookies.exists() and local_storage.exists()
    assert freed > 0
