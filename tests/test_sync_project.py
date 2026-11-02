import pytest
import yaml

from scripts.sync_project import copy_toolkit, write_version


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"version": "1.4.0"}', encoding="utf-8")
    (root / "skills" / "db-access").mkdir(parents=True)
    (root / "skills" / "db-access" / "SKILL.md").write_text(
        "---\nname: db-access\ndescription: 测试\n---\n\n正文 <TOOLS_DIR>\n",
        encoding="utf-8",
    )
    (root / "skills" / "_TEMPLATE").mkdir()
    (root / "skills" / "_TEMPLATE" / "project-readme.md").write_text("# <PROJECT_ID>\n", encoding="utf-8")
    (root / "runtime").mkdir()
    (root / "runtime" / "__init__.py").write_text("", encoding="utf-8")
    (root / "runtime" / "__pycache__").mkdir()
    (root / "runtime" / "__pycache__" / "x.pyc").write_text("", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
    (root / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
    (root / "bootstrap.ps1").write_text("# bootstrap\n", encoding="utf-8")
    (root / "update.ps1").write_text("# update\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "x.py").write_text("", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("", encoding="utf-8")
    return root


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return path


def test_copy_toolkit_copies_whitelist_and_skips_caches(source, project):
    copied = copy_toolkit(source, project)
    dest = project / "data-tools"
    assert (dest / "skills" / "db-access" / "SKILL.md").exists()
    assert (dest / "requirements.txt").exists()
    assert (dest / "scripts" / "sync_project.py").exists()
    assert not (dest / ".venv").exists()
    assert not (dest / "__pycache__").exists()
    assert not (dest / "runtime" / "__pycache__").exists()
    assert all(path.exists() for path in copied)


def test_write_version_reads_plugin_version(source, project):
    path = write_version(source, project, "https://example.com/claudeTool.git")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["version"] == "1.4.0"
    assert data["source"] == "https://example.com/claudeTool.git"
    assert data["source_commit"] == "unknown"