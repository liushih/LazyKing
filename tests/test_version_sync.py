import json
import re
from pathlib import Path

import pytest

from scripts.bump_version import MANIFESTS, bump, current_version, main

ROOT = Path(__file__).resolve().parents[1]


def _load(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def test_manifests_share_one_version():
    versions = {rel: _load(ROOT, rel)["version"] for rel in MANIFESTS}
    assert len(set(versions.values())) == 1, versions
    assert re.fullmatch(r"\d+\.\d+\.\d+", current_version(ROOT))


def test_marketplace_does_not_repeat_the_version():
    market = _load(ROOT, ".claude-plugin/marketplace.json")
    assert "version" not in market.get("metadata", {})
    assert all("version" not in plugin for plugin in market["plugins"])


@pytest.fixture
def fake_root(tmp_path):
    for rel in MANIFESTS:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{\n  "name": "x",\n  "version": "1.0.0",\n  "description": "d"\n}\n', encoding="utf-8")
    return tmp_path


def test_bump_updates_every_manifest_and_keeps_other_fields(fake_root):
    bump(fake_root, "2.3.4")
    for rel in MANIFESTS:
        data = _load(fake_root, rel)
        assert data["version"] == "2.3.4"
        assert data["description"] == "d"


@pytest.mark.parametrize("bad", ["2.3", "v2.3.4", "2.3.4-rc1", "", "a.b.c"])
def test_bump_rejects_non_semver(fake_root, bad):
    with pytest.raises(ValueError, match="版本号"):
        bump(fake_root, bad)
    assert current_version(fake_root) == "1.0.0"


def test_cli_prints_new_version(fake_root, capsys):
    assert main(["--root", str(fake_root), "1.2.3"]) == 0
    assert "1.2.3" in capsys.readouterr().out
    assert main(["--root", str(fake_root), "bad"]) == 2
