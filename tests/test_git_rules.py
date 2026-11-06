import pytest

from runtime.git_host.rules import (
    RuleViolation,
    check_branch_name,
    check_commit_message,
    check_commit_paths,
    check_merge,
    check_sync,
    parse_branch,
)


def test_parse_branch_accepts_chinese_description():
    info = parse_branch("feature/test/lsh/15579-FMS运费推送补全")
    assert info.target == "test" and info.user_tag == "lsh"
    assert info.task == "15579" and info.desc == "FMS运费推送补全"


def test_parse_branch_rejects_missing_task():
    assert parse_branch("feature/test/lsh/no-task") is None


def test_check_branch_name_requires_matching_user_tag():
    with pytest.raises(RuleViolation) as exc:
        check_branch_name("feature/test/other/15579-x", user_tag="lsh")
    assert exc.value.rule == "branch-naming"


def test_check_branch_name_rejects_space_in_desc():
    with pytest.raises(RuleViolation):
        check_branch_name("feature/test/lsh/15579-a b", user_tag="lsh")


def test_check_commit_message_accepts_feat_with_body():
    check_commit_message("feat-15579: 补全运费推送\n\n按平台拆分批次后再推送。")


def test_check_commit_message_rejects_missing_body():
    with pytest.raises(RuleViolation) as exc:
        check_commit_message("feat-15579: 补全运费推送")
    assert exc.value.rule == "commit-message"


def test_check_commit_message_rejects_conventional_style():
    with pytest.raises(RuleViolation):
        check_commit_message("feat(wms): 补全\n\n正文")


def test_check_commit_paths_blocks_pom():
    with pytest.raises(RuleViolation) as exc:
        check_commit_paths(["src/a.java", "pom.xml"], ["pom.xml", "vite.config.ts"])
    assert exc.value.rule == "forbidden-path"
    assert "pom.xml" in exc.value.message


def test_check_commit_paths_allows_clean_set():
    check_commit_paths(["src/a.java"], ["pom.xml"])


def test_merge_to_test_is_direct_violation():
    with pytest.raises(RuleViolation) as exc:
        check_merge("feature/dev/lsh/1-x", "test", None, [])
    assert exc.value.rule == "direct-merge"


def test_merge_to_prod_is_direct_violation():
    with pytest.raises(RuleViolation):
        check_merge("feature/dev/lsh/1-x", "prod", None, [])


def test_merge_prod_derived_into_dev_is_blocked():
    with pytest.raises(RuleViolation) as exc:
        check_merge("feature/prod/lsh/1-x", "dev", "prod", [])
    assert exc.value.rule == "prod-derived"


def test_merge_feature_test_with_foreign_commits_returns_confirmation_list():
    assert check_merge("feature/test/lsh/1-x", "dev", "test", ["abc123"]) == ["abc123"]


def test_merge_feature_test_with_no_foreign_commits_passes():
    assert check_merge("feature/test/lsh/1-x", "dev", "test", []) == []


def test_sync_source_defaults_to_branch_target():
    assert check_sync("feature/test/lsh/1-x", None) == "test"


def test_sync_source_must_match_branch_target():
    with pytest.raises(RuleViolation) as exc:
        check_sync("feature/test/lsh/1-x", "dev")
    assert exc.value.rule == "sync-source"


def test_sync_uses_target_prefix_when_task_missing():
    assert check_sync("feature/test/lsh/整合LazyKing", None) == "test"


def test_sync_explicit_source_matches_target_prefix():
    assert check_sync("feature/test/lsh/整合LazyKing", "test") == "test"


def test_sync_explicit_source_still_rejects_other_target():
    with pytest.raises(RuleViolation) as exc:
        check_sync("feature/test/lsh/整合LazyKing", "dev")
    assert exc.value.rule == "sync-source"


def test_sync_explicit_source_allows_non_feature_branch():
    assert check_sync("claude/whatever", "test") == "test"


def test_sync_non_feature_branch_without_source_asks_for_from():
    with pytest.raises(RuleViolation) as exc:
        check_sync("claude/whatever", None)
    assert exc.value.rule == "branch-naming"
    assert "--from" in exc.value.message


def test_sync_requires_feature_branch_name():
    with pytest.raises(RuleViolation) as exc:
        check_sync("dev", None)
    assert exc.value.rule == "branch-naming"


def test_merge_dev_feature_into_dev_passes():
    assert check_merge("feature/dev/lsh/1-x", "dev", "dev", []) == []
