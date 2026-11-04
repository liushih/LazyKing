import subprocess
from pathlib import Path

import pytest

from runtime.jenkins.config import ModuleSpec
from runtime.jenkins.modules import ModulesError, changed_files, infer_modules, unpushed_commits


def _mod(name, *paths):
    return ModuleSpec(name=name, paths=list(paths), jobs={"dev": f"{name}-dev"})


def test_longest_prefix_wins():
    a, b = _mod("a", "svc/"), _mod("b", "svc/sub/")
    hit, unmapped = infer_modules(["svc/sub/x.py"], [a, b])
    assert [m.name for m in hit] == ["b"]
    hit, _ = infer_modules(["svc/y.py"], [a, b])
    assert [m.name for m in hit] == ["a"]
    assert unmapped == []


def test_result_keeps_yaml_order_and_dedupes():
    a, b = _mod("a", "a/"), _mod("b", "b/")
    hit, _ = infer_modules(["b/1.py", "a/1.py", "b/2.py"], [a, b])
    assert [m.name for m in hit] == ["a", "b"]


def test_unmapped_files_listed():
    a = _mod("a", "a/")
    hit, unmapped = infer_modules(["a/1.py", "docs/readme.md"], [a])
    assert [m.name for m in hit] == ["a"]
    assert unmapped == ["docs/readme.md"]


def test_prefix_matches_directory_boundary():
    order = _mod("order", "order/")
    hit, unmapped = infer_modules(["order-service/x.py"], [order])
    assert hit == []
    assert unmapped == ["order-service/x.py"]


def test_backslash_paths_normalised():
    order = _mod("order", "order/")
    hit, _ = infer_modules(["order\\x.py"], [order])
    assert [m.name for m in hit] == ["order"]


def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    import os

    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        env={**os.environ, **env}, check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, rel: str, text: str = "x") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "README.md")
    return root


def test_changed_files_against_baseline(repo):
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "svc/a.py")
    (repo / "uncommitted.py").write_text("y", encoding="utf-8")
    assert changed_files(repo, "main") == ["svc/a.py"]


def test_changed_files_same_as_baseline_is_empty(repo):
    assert changed_files(repo, "main") == []


def test_changed_files_bad_baseline_raises_friendly_error(repo):
    with pytest.raises(ModulesError) as exc:
        changed_files(repo, "origin/nope")
    assert "origin/nope" in str(exc.value)


def test_unpushed_commits(repo, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "svc/a.py")
    assert unpushed_commits(repo, "feat") is None
    _git(repo, "push", "-q", "origin", "feat")
    assert unpushed_commits(repo, "feat") == 0
    _commit(repo, "svc/b.py")
    assert unpushed_commits(repo, "feat") == 1


def test_current_branch(repo):
    from runtime.jenkins.modules import current_branch

    assert current_branch(repo) == "main"
    _git(repo, "checkout", "-q", "-b", "feature/x")
    assert current_branch(repo) == "feature/x"


def test_uncommitted_files_lists_modified_and_untracked(repo):
    from runtime.jenkins.modules import uncommitted_files

    assert uncommitted_files(repo) == []
    (repo / "README.md").write_text("changed", encoding="utf-8")
    (repo / "svc").mkdir()
    (repo / "svc" / "new.py").write_text("x", encoding="utf-8")
    assert sorted(uncommitted_files(repo)) == ["README.md", "svc/new.py"]
