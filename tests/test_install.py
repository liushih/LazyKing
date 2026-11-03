from pathlib import Path

import pytest

from scripts.install import install, main, remove, skill_names

NAMES = ("data-gen-core", "db-access", "adapter-bootstrap", "report-writer", "git-workflow")


@pytest.fixture
def tools(tmp_path):
    root = tmp_path / "tools"
    for name in NAMES:
        d = root / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} 测试\n---\n\n# {name}\n\n正文 <TOOLS_DIR>\n",
            encoding="utf-8",
        )
    return root


def test_skill_names_discovers_browser_test(tmp_path):
    path = tmp_path / "skills" / "browser-test"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: browser-test\ndescription: 测试\n---\n", encoding="utf-8")
    assert "browser-test" in skill_names(tmp_path)


def test_claude_skill_has_name_and_description(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    by_name = {p.parent.name: p for p in paths}
    text = by_name["data-gen-core"].read_text(encoding="utf-8")
    assert "name: data-gen-core" in text
    assert "description:" in text
    assert by_name["data-gen-core"].name == "SKILL.md"


def test_tools_dir_placeholder_is_replaced(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    text = paths[0].read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" not in text
    assert tools.as_posix() in text


def test_cursor_rule_has_always_apply(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["cursor"], "project", repo, tools, home=tmp_path)
    target = next(p for p in paths if p.stem == "data-gen-core")
    text = target.read_text(encoding="utf-8")
    assert "alwaysApply: false" in text
    assert target.suffix == ".mdc"


def test_codex_block_is_not_duplicated(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, tools, home=tmp_path)
    install(["codex"], "project", repo, tools, home=tmp_path)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("data-tools:begin") == 1


def test_remove_deletes_generated(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["cursor"], "project", repo, tools, home=tmp_path)
    remove(["cursor"], "project", repo, home=tmp_path, tools_dir=tools)
    assert not (repo / ".cursor" / "rules" / "data-gen-core.mdc").exists()


def test_generated_claude_file_starts_with_frontmatter(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    assert paths
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith("---\n")


def test_generated_cursor_file_starts_with_frontmatter(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["cursor"], "project", repo, tools, home=tmp_path)
    assert paths
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith("---\n")


def test_remove_without_project_dir_skips_project_tools(tmp_path, tools):
    install(["claude"], "global", None, tools, home=tmp_path)
    remove(["claude", "cursor", "codex"], "global", None, home=tmp_path, tools_dir=tools)
    assert not (tmp_path / ".claude" / "skills" / "data-gen-core" / "SKILL.md").exists()


def test_dsh_skill_lands_in_dsh_home(tmp_path, tools):
    paths = install(["dsh"], "global", None, tools, home=tmp_path)
    target = tmp_path / ".dsh" / "skills" / "data-gen-core" / "SKILL.md"
    assert target.exists() and target in paths
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: data-gen-core" in text
    assert "<TOOLS_DIR>" not in text


def test_dsh_project_scope_writes_into_repo(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["dsh"], "project", repo, tools, home=tmp_path)
    assert (repo / ".dsh" / "skills" / "db-access" / "SKILL.md").exists()
    assert all(str(p).startswith(str(repo)) for p in paths)


def test_dsh_remove_cleans_up(tmp_path, tools):
    install(["dsh"], "global", None, tools, home=tmp_path)
    remove(["dsh"], "global", None, home=tmp_path, tools_dir=tools)
    assert not (tmp_path / ".dsh" / "skills" / "data-gen-core").exists()


def _make_skill(root: Path, name: str) -> None:
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} 测试\n---\n\n# {name}\n", encoding="utf-8"
    )


def test_new_skill_directory_is_installed_without_code_change(tmp_path):
    root = tmp_path / "tools"
    _make_skill(root, "brand-new")
    install(["dsh"], "global", None, root, home=tmp_path)
    assert (tmp_path / ".dsh" / "skills" / "brand-new" / "SKILL.md").exists()


def test_underscore_directory_is_not_installed(tmp_path):
    root = tmp_path / "tools"
    _make_skill(root, "_TEMPLATE")
    paths = install(["dsh"], "global", None, root, home=tmp_path)
    assert paths == []
    assert not (tmp_path / ".dsh" / "skills" / "_TEMPLATE").exists()


def test_codex_block_lists_discovered_skills(tmp_path):
    root = tmp_path / "tools"
    _make_skill(root, "alpha")
    _make_skill(root, "beta")
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, root, home=tmp_path)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "alpha" in text
    assert "beta" in text


def test_portable_render_keeps_placeholder(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["claude"], "project", repo, tools, home=tmp_path, portable=True)
    text = paths[0].read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" in text
    assert tools.as_posix() not in text


def test_portable_codex_block_points_to_project_tools(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, tools, home=tmp_path, portable=True)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "data-tools/skills" in text
    assert tools.as_posix() not in text


def test_cli_rejects_portable_with_global_scope(tmp_path, tools, capsys):
    code = main(
        [
            "--target",
            "claude",
            "--scope",
            "global",
            "--portable",
            "--tools-dir",
            str(tools),
            "--home",
            str(tmp_path),
        ]
    )
    assert code == 2
    assert "--portable" in capsys.readouterr().err
    assert not (tmp_path / ".claude" / "skills").exists()
