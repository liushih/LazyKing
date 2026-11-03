import os
import subprocess

import pytest

from runtime.git_host.repo import Repo, RepoError
from runtime.git_host.rules import RuleViolation


def _git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _init(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "config", "user.email", "t@x.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _commit(repo, name, message):
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_commit_rejects_bad_message(tmp_path):
    repo = _init(tmp_path)
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "b.txt")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).commit("随便写写", forbidden=["pom.xml"])
    assert exc.value.rule == "commit-message"


def test_commit_rejects_forbidden_staged_path(tmp_path):
    repo = _init(tmp_path)
    (repo / "pom.xml").write_text("<project/>", encoding="utf-8")
    _git(repo, "add", "pom.xml")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).commit("feat-1: 调整\n\n正文说明。", forbidden=["pom.xml"])
    assert exc.value.rule == "forbidden-path"


def test_commit_succeeds_with_valid_message(tmp_path):
    repo = _init(tmp_path)
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "b.txt")
    short = Repo(repo).commit("feat-1: 新增 b\n\n添加 b.txt 用于测试。", forbidden=["pom.xml"])
    assert len(short) >= 7


def test_bring_in_is_empty_for_clean_branch(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    assert Repo(repo).bring_in_commits("feature/dev/lsh/1-x", "dev", base="dev") == []


def test_bring_in_lists_base_commits_missing_from_target(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "test")
    test_tip = _commit(repo, "t.txt", "feat-2: t\n\nt")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    assert Repo(repo).bring_in_commits("feature/test/lsh/1-x", "dev", base="test") == [test_tip]


def test_fork_base_picks_closest_ancestor(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "test")
    _commit(repo, "t.txt", "feat-2: t\n\nt")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    assert Repo(repo).fork_base("feature/test/lsh/1-x") == "test"


def test_merge_conflict_keeps_scene_and_lists_files(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x")
    (repo / "a.txt").write_text("from-feature", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-1: f\n\nf")
    _git(repo, "checkout", "-q", "dev")
    (repo / "a.txt").write_text("from-dev", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-2: d\n\nd")
    with pytest.raises(RepoError) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert "a.txt" in str(exc.value)
    assert "git merge --abort" in str(exc.value)
    assert "UU a.txt" in _git(repo, "status", "--porcelain")


def _with_remote(tmp_path):
    """origin 为裸库，含 dev/test；返回 (工作库, 另一份克隆用于模拟同事推送)。"""
    repo = _init(tmp_path)
    bare = tmp_path / "origin.git"
    _git(repo, "init", "-q", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "branch", "test")
    _git(repo, "push", "-q", "origin", "dev", "test")
    mate = tmp_path / "mate"
    subprocess.run(["git", "clone", "-q", str(bare), str(mate)], check=True, capture_output=True)
    _git(mate, "config", "user.email", "m@x.com")
    _git(mate, "config", "user.name", "m")
    _git(mate, "checkout", "-q", "-B", "dev", "origin/dev")
    return repo, mate


def test_merge_to_dev_fast_forwards_stale_local_dev_first(tmp_path):
    repo, mate = _with_remote(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x", "dev")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    _commit(mate, "m.txt", "feat-2: m\n\nm")
    _git(mate, "push", "-q", "origin", "dev")
    Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert (repo / "m.txt").exists() and (repo / "c.txt").exists()
    assert _git(repo, "rev-list", "--count", "origin/dev..dev") != "0"


def test_merge_to_dev_refuses_diverged_local_dev(tmp_path):
    repo, mate = _with_remote(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x", "dev")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    _git(repo, "checkout", "-q", "dev")
    _commit(repo, "local.txt", "feat-3: l\n\nl")
    _commit(mate, "m.txt", "feat-2: m\n\nm")
    _git(mate, "push", "-q", "origin", "dev")
    before = _git(repo, "rev-parse", "dev")
    with pytest.raises(RepoError) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert "已分叉" in str(exc.value)
    assert _git(repo, "rev-parse", "dev") == before


def test_merge_refuses_dirty_tracked_files(tmp_path):
    repo = _init(tmp_path)
    (repo / "a.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(RepoError) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert "未提交" in str(exc.value)


def test_merge_ignores_untracked_files(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dev/lsh/1-x")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    _git(repo, "checkout", "-q", "dev")
    (repo / "scratch.txt").write_text("x", encoding="utf-8")
    Repo(repo).merge("feature/dev/lsh/1-x", "dev", None, forbidden_targets=["test", "prod"])
    assert (repo / "c.txt").exists()


def test_sync_brings_latest_test_into_feature_branch(tmp_path):
    repo, mate = _with_remote(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x", "origin/test")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    _git(mate, "checkout", "-q", "test")
    _commit(mate, "m.txt", "feat-2: m\n\nm")
    _git(mate, "push", "-q", "origin", "test")
    assert Repo(repo).sync() == 1
    assert (repo / "m.txt").exists()
    assert Repo(repo).sync() == 0


def test_sync_refuses_foreign_source(tmp_path):
    repo, _ = _with_remote(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x", "origin/test")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).sync("dev")
    assert exc.value.rule == "sync-source"


def test_sync_refuses_non_feature_branch(tmp_path):
    repo, _ = _with_remote(tmp_path)
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).sync()
    assert exc.value.rule == "branch-naming"


def test_sync_conflict_keeps_scene(tmp_path):
    repo, mate = _with_remote(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x", "origin/test")
    (repo / "a.txt").write_text("mine", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-1: f\n\nf")
    _git(mate, "checkout", "-q", "test")
    (mate / "a.txt").write_text("theirs", encoding="utf-8")
    _git(mate, "commit", "-qam", "feat-2: t\n\nt")
    _git(mate, "push", "-q", "origin", "test")
    with pytest.raises(RepoError) as exc:
        Repo(repo).sync()
    assert "a.txt" in str(exc.value)
    assert "UU a.txt" in _git(repo, "status", "--porcelain")


def test_merge_to_test_is_refused_before_touching_git(tmp_path):
    repo = _init(tmp_path)
    before = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).merge("feature/dev/lsh/1-x", "test", None, forbidden_targets=["test", "prod"])
    assert exc.value.rule == "direct-merge"
    assert _git(repo, "rev-parse", "HEAD") == before


def test_create_branch_is_independent_of_target(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "fetch", "-q", "origin")
    Repo(repo).create_branch("feature/dev/lsh/1-x", target="dev")
    assert _git(repo, "rev-list", "--count", "origin/dev..HEAD") == "0"
    assert _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False) == ""


def test_push_to_non_matching_remote_is_refused(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "test")
    with pytest.raises(RuleViolation) as exc:
        Repo(repo).push("test")
    assert exc.value.rule == "push-target"


def test_push_dev_is_allowed(tmp_path):
    repo, _ = _with_remote(tmp_path)
    _commit(repo, "d.txt", "feat-1: d\n\nd")
    Repo(repo).push("dev")
    assert _git(repo, "rev-parse", "origin/dev") == _git(repo, "rev-parse", "dev")


def test_hotfix_commits_lists_all_fix_commits_in_order(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "prod")
    _git(repo, "checkout", "-q", "-b", "feature/prod/lsh/1-hot")
    first = _commit(repo, "one.txt", "fix-1: one\n\none")
    second = _commit(repo, "two.txt", "fix-1: two\n\ntwo")
    assert Repo(repo).hotfix_commits("feature/prod/lsh/1-hot", prod_ref="prod") == [first, second]


def test_hotfix_commits_empty_is_error(tmp_path):
    repo = _init(tmp_path)
    with pytest.raises(RepoError):
        Repo(repo).hotfix_commits("dev", prod_ref="dev")


def test_cherry_pick_brings_content_not_hash(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/prod/lsh/1-hot")
    hot = _commit(repo, "fix.txt", "fix-1: 热修\n\n修正。")
    _git(repo, "checkout", "-q", "dev")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-sync")
    new = Repo(repo).cherry_pick([hot])
    assert len(new) == 1
    assert _git(repo, "rev-parse", "HEAD") != hot
    assert (repo / "fix.txt").read_text(encoding="utf-8") == "fix.txt"


def test_cherry_pick_conflict_aborts_and_lists_files(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/prod/lsh/1-hot")
    (repo / "a.txt").write_text("hot", encoding="utf-8")
    _git(repo, "commit", "-qam", "fix-1: h\n\nh")
    hot = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "dev")
    (repo / "a.txt").write_text("other", encoding="utf-8")
    _git(repo, "commit", "-qam", "feat-2: o\n\no")
    with pytest.raises(RepoError) as exc:
        Repo(repo).cherry_pick([hot])
    assert "a.txt" in str(exc.value)
    assert _git(repo, "status", "--porcelain") == ""


def test_check_prod_derived_only_blocks_dev_and_test(tmp_path):
    repo = _init(tmp_path)
    r = Repo(repo)
    with pytest.raises(RuleViolation) as exc:
        r.check_prod_derived("prod", "dev")
    assert exc.value.rule == "prod-derived"
    r.check_prod_derived("prod", "feature/test/lsh/1-sync")


def test_verify_flow_flags_prod_only_commits(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "branch", "test")
    _git(repo, "checkout", "-q", "-b", "prod")
    hot = _commit(repo, "hot.txt", "fix-9: 线上\n\n线上修复。")
    _git(repo, "checkout", "-q", "dev")
    _git(repo, "update-ref", "refs/remotes/origin/test", "test")
    _git(repo, "update-ref", "refs/remotes/origin/prod", "prod")
    _git(repo, "update-ref", "refs/remotes/origin/dev", "dev")
    report = Repo(repo).verify_flow("prod", "test", "dev")
    assert hot in report.prod_only
    assert report.safe is False


def test_verify_flow_is_read_only(tmp_path):
    repo = _init(tmp_path)
    _git(repo, "branch", "prod")
    _git(repo, "branch", "test")
    _git(repo, "checkout", "-q", "-b", "feature/test/lsh/1-x")
    _commit(repo, "c.txt", "feat-1: c\n\nc")
    before_head = _git(repo, "rev-parse", "HEAD")
    before_refs = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    report = Repo(repo).verify_flow("prod", "test", "dev")
    assert _git(repo, "rev-parse", "HEAD") == before_head
    assert _git(repo, "for-each-ref", "--format=%(refname) %(objectname)") == before_refs
    assert report.safe is True
