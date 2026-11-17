import json
from pathlib import Path

from runtime.browser.resume import (
    clear_state,
    flow_fingerprint,
    load_state,
    save_state,
    seed_fingerprint,
    state_path,
)


def test_state_roundtrip_drops_secret_keys(tmp_path):
    path = state_path(tmp_path, "demo", "dev", "smoke")
    save_state(
        path,
        flow_hash="f1",
        seed_hash="s1",
        env="dev",
        completed=2,
        produced={"out_no": "WO1", "api_token": "secret", "PASSWORD": "x"},
    )
    saved = load_state(path, flow_hash="f1", seed_hash="s1", env="dev", step_count=5)
    assert saved == {"completed": 2, "produced": {"out_no": "WO1"}}


def test_load_rejects_changed_flow_seed_or_env(tmp_path):
    path = state_path(tmp_path, "demo", "dev", "smoke")
    save_state(path, flow_hash="f1", seed_hash="s1", env="dev", completed=2, produced={})
    assert load_state(path, flow_hash="f2", seed_hash="s1", env="dev", step_count=5) is None
    assert load_state(path, flow_hash="f1", seed_hash="s2", env="dev", step_count=5) is None
    assert load_state(path, flow_hash="f1", seed_hash="s1", env="test", step_count=5) is None


def test_load_rejects_completed_outside_step_range(tmp_path):
    path = state_path(tmp_path, "demo", "dev", "smoke")
    save_state(path, flow_hash="f1", seed_hash="s1", env="dev", completed=5, produced={})
    assert load_state(path, flow_hash="f1", seed_hash="s1", env="dev", step_count=5) is None
    save_state(path, flow_hash="f1", seed_hash="s1", env="dev", completed=0, produced={})
    assert load_state(path, flow_hash="f1", seed_hash="s1", env="dev", step_count=5) is None


def test_load_ignores_corrupt_state(tmp_path):
    path = state_path(tmp_path, "demo", "dev", "smoke")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_state(path, flow_hash="f1", seed_hash="s1", env="dev", step_count=5) is None


def test_flow_fingerprint_follows_file_content(tmp_path):
    path = tmp_path / "flow.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    first = flow_fingerprint(path)
    path.write_text("version: 1\nflow: x\n", encoding="utf-8")
    assert first and first != flow_fingerprint(path)
    assert flow_fingerprint(tmp_path / "missing.yaml") == ""


def test_seed_fingerprint_is_order_independent():
    assert seed_fingerprint({"b": "2", "a": "1"}) == seed_fingerprint({"a": "1", "b": "2"})


def test_clear_state_removes_file_and_ignores_missing(tmp_path):
    path = state_path(tmp_path, "demo", "dev", "smoke")
    save_state(path, flow_hash="f1", seed_hash="s1", env="dev", completed=1, produced={})
    clear_state(path)
    assert not path.exists()
    clear_state(path)
