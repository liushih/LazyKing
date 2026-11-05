from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[1] / "skills"
SKILL_NAMES = [
    "data-gen-core",
    "db-access",
    "adapter-bootstrap",
    "report-writer",
    "git-workflow",
    "browser-test",
    "jenkins-deploy",
    "project-setup",
]


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_has_frontmatter_and_sections(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    for section in ["## 适用场景", "## 前置检查", "## 执行", "## 失败处理"]:
        assert section in text


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_commands_are_single_line(name):
    """命令块里不留 bash 反斜杠续行，PowerShell（DSH on Windows）会把它断成多条命令。"""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    offenders = [line for line in text.splitlines() if line.rstrip().endswith("\\")]
    assert offenders == [], f"{name} 仍有续行：{offenders}"


def test_report_skill_asks_audience_and_scope():
    text = (SKILLS / "report-writer" / "SKILL.md").read_text(encoding="utf-8")
    assert "给谁" in text
    assert "不猜" in text
    assert "collect.py" in text


def test_report_skill_asks_role():
    text = (SKILLS / "report-writer" / "SKILL.md").read_text(encoding="utf-8")
    assert "角色" in text
    assert ".role" in text
    for role in ["开发", "测试", "产品"]:
        assert role in text


def test_db_access_covers_redis_and_mongo():
    text = (SKILLS / "db-access" / "SKILL.md").read_text(encoding="utf-8")
    assert "redis.py" in text
    assert "mongo.py" in text


def test_data_gen_requires_adapter_and_forbids_improvisation():
    text = (SKILLS / "data-gen-core" / "SKILL.md").read_text(encoding="utf-8")
    assert "adapter-bootstrap" in text
    assert "不允许现场推导" in text


def test_trigger_routing_covers_all_intents():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    for word in ["造数", "连库", "接入", "报告", "沉淀", "个人配置"]:
        assert word in text
    assert "project-setup" in text
    assert "report-writer" in text


def test_adapter_example_parses():
    data = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "adapter.example.yaml").read_text(encoding="utf-8")
    )
    assert data["version"] == 1 and "entities" in data


def test_git_skill_requires_user_tag_and_confirmation():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "user_tag" in text
    assert "set-user-tag" in text
    assert "回显" in text
    assert "确认" in text
    assert "git_host.py" in text


def test_git_skill_forbids_pasting_token_in_chat():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "不要让用户把令牌贴进对话" in text


def test_git_skill_routes_test_and_prod_merge_to_mr():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "mr create" in text
    assert "test" in text and "prod" in text


def test_git_skill_reports_existing_mr_on_conflict():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "409" in text and "422" in text
    assert "已存在" in text


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_has_environment_preflight(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert "## 第 0 步：环境检查" in text
    assert "Python 3.11+" in text
    assert "bootstrap.ps1" in text
    assert "update.ps1 -CheckOnly -Quiet" in text
    assert "是否现在更新" in text
    assert "data-tools/" in text
    assert (SKILLS / "_references" / "project-layout.md").exists()

    # 与 runtime/config.py 的 data_home() 一致：环境变量优先于向上查找。
    step2 = next(line for line in text.splitlines() if line.startswith("2. 定位 <DATA_HOME>"))
    assert step2.index("DATA_TOOLS_HOME") < step2.index(".data-tools/")


def test_browser_skill_memory_and_safety_rules():
    text = (SKILLS / "browser-test" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["不写固定 sleep", "probe", "diagnosis.md", "pitfalls.md", "退出码 0", "browser.py"]:
        assert word in text
    assert "track_shared.py" in text
    assert "不要询问" in text
    assert "git add -f" not in text or "不要加 `-f`" in text


def test_browser_examples_parse():
    browser_cfg = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "browser.example.yaml").read_text(encoding="utf-8")
    )
    flow = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "browser-flow.example.yaml").read_text(encoding="utf-8")
    )
    assert browser_cfg["version"] == 1 and "login" in browser_cfg
    assert flow["version"] == 1 and flow["steps"]


def test_trigger_routing_includes_browser():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    assert "浏览器" in text and "browser-test" in text


def test_jenkins_skill_confirms_before_build_and_protects_token():
    text = (SKILLS / "jenkins-deploy" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["--dry-run", "确认", "stdin", "不回显", "403", "discover", "jenkins.py"]:
        assert word in text


def test_trigger_routing_includes_jenkins():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    assert "发版" in text and "Jenkins" in text and "jenkins-deploy" in text
    assert "七个 skill" not in text and "八个 skill" in text


def test_jenkins_example_parses():
    data = yaml.safe_load((SKILLS / "_TEMPLATE" / "jenkins.example.yaml").read_text(encoding="utf-8"))
    assert {"base_url", "user", "token_key"} <= set(data["jenkins"])
    assert data["baseline"]
    module = next(iter(data["modules"].values()))
    assert {"paths", "jobs", "params"} <= set(module)


def test_env_example_has_jenkins_token():
    assert "JENKINS_TOKEN" in (SKILLS / "_TEMPLATE" / "env.example").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_every_capability_skill_checks_personal_config(name):
    if name == "project-setup":
        return
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert "config.py" in text and "check" in text
    assert "project-setup" in text


def test_project_setup_skill_documents_flow():
    text = (SKILLS / "project-setup" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["config.py", "check", "set-secret", "personal.yaml", "不猜", "不回显"]:
        assert word in text
