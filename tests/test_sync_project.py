import pytest
import yaml

from scripts.sync_project import copy_toolkit, write_version
from scripts.sync_project import render_targets, upsert_gitignore
from scripts.sync_project import init_data_dirs, sync_project


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


def test_render_targets_keeps_tools_dir_placeholder(source, project):
    paths = render_targets(source, project, ["claude"])
    text = (project / ".claude" / "skills" / "db-access" / "SKILL.md").read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" in text
    assert paths


def test_upsert_gitignore_is_idempotent(project):
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    upsert_gitignore(project)
    upsert_gitignore(project)
    text = (project / ".gitignore").read_text(encoding="utf-8")
    assert text.count("# data-tools:begin") == 1
    assert "node_modules/" in text
    assert "data-tools/.venv/" in text


def test_init_data_dirs_preserves_existing(source, project):
    project_path = project / ".data-tools" / "projects" / "demo"
    project_path.mkdir(parents=True)
    (project_path / "adapter.yaml").write_text("version: 1\n", encoding="utf-8")
    (project_path / "pitfalls.md").write_text("### P1\n", encoding="utf-8")
    (project_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    init_data_dirs(project, "demo")
    assert (project_path / "adapter.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert (project_path / "pitfalls.md").read_text(encoding="utf-8") == "### P1\n"
    assert (project_path / ".env").read_text(encoding="utf-8") == "SECRET=1\n"
    assert (project_path / ".env.example").exists()
    assert "default_project: demo" in (project / ".data-tools" / "config.yaml").read_text(encoding="utf-8")


def test_sync_project_end_to_end(source, project):
    result = sync_project(project, "demo", ("claude",), source)
    assert (project / "data-tools" / "VERSION").exists()
    assert (project / ".claude" / "skills" / "db-access" / "SKILL.md").exists()
    assert (project / "data-tools" / "README.md").exists()
    assert (project / ".gitignore").exists()
    assert result.copied


def test_sync_project_dry_run_writes_nothing(source, project):
    sync_project(project, "demo", ("claude",), source, dry_run=True)
    assert not (project / "data-tools").exists()


def test_sync_project_missing_core_item_raises(source, project):
    (source / "requirements.txt").unlink()
    with pytest.raises(FileNotFoundError, match="requirements.txt"):
        sync_project(project, "demo", ("claude",), source)
