# 分支默认基线可配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让新分支的默认基线由项目级 `git_hosts.yaml` 的 `rules.default_branch_target` 决定，未配置时仍从 `origin/test` 切。

**Architecture:** 配置层给 `GitHostConfig` 增加 `default_branch_target` 并做取值校验；CLI 的 `branch create --target` 从必填改为可选，省略时读取配置；技能规则同步改为读配置。执行引擎、分支命名、sync/merge 规则不动。

**Tech Stack:** Python 3.11+、argparse、PyYAML、pytest。

**Spec:** `docs/superpowers/specs/2026-11-16-configurable-branch-base-design.md`

## Global Constraints

- 配置键固定为 `git_hosts.yaml` 的 `rules.default_branch_target`，取值只能是 `dev` / `test` / `prod`。
- 键缺省或为 `null` 时等价于 `test`；显式空字符串或非法值必须报配置错误，不猜。
- `branch create --target` 显式传入时优先于配置。
- 不改变分支命名、`sync`、`merge` 的现有规则。
- 本次改动运行行为，版本升到 `2.9.0`，用 `scripts/bump_version.py`，不手改清单。
- 全量测试命令：`.venv/Scripts/python.exe -m pytest tests -q`。

## Review Focus

- 配置段整段缺失 → 按 `test` 工作，不报错。
- `default_branch_target: ""` → 报配置错误，而不是悄悄回退到 `test`。
- 配置为 `dev`、调用方又显式传 `--target test` → 以显式值为准。
- 配置为 `prod` → 合法（热修场景），切分支走 `origin/prod`，其余规则不变。
- 技能文案与 CLI 的默认值必须一致，`tests/test_skills.py` 要钉住 `default_branch_target` 出现在技能中。

---

### Task 1: 配置读取 `default_branch_target`

**Files:**
- Modify: `runtime/git_host/config.py:20-29`（`GitHostConfig`）、`runtime/git_host/config.py:53-63`（`load_git_host_config` 的 `rules` 解析）
- Test: `tests/test_git_host_config.py`

**Interfaces:**
- Consumes: 现有 `load_git_host_config(project_id, home=None) -> GitHostConfig`
- Produces: `GitHostConfig.default_branch_target: str`，取值为 `"dev" | "test" | "prod"`，缺省 `"test"`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_git_host_config.py` 末尾追加：

```python
def test_default_branch_target_defaults_to_test(home):
    assert load_git_host_config("demo", home=home).default_branch_target == "test"


def test_reads_default_branch_target(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(
        YAML.replace("rules:\n", "rules:\n  default_branch_target: dev\n"),
        encoding="utf-8",
    )
    assert load_git_host_config("demo", home=home).default_branch_target == "dev"


def test_prod_default_branch_target_is_allowed(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(
        YAML.replace("rules:\n", "rules:\n  default_branch_target: prod\n"),
        encoding="utf-8",
    )
    assert load_git_host_config("demo", home=home).default_branch_target == "prod"


def test_missing_rules_section_defaults_to_test(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        "user_tag: lsh\n"
        "repo_path: C:/project/demo\n"
        "host: {kind: gitlab, base_url: http://g, project_path: a/b, token_key: T}\n",
        encoding="utf-8",
    )
    assert load_git_host_config("demo", home=tmp_path).default_branch_target == "test"


def test_invalid_default_branch_target_rejected(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(
        YAML.replace("rules:\n", "rules:\n  default_branch_target: main\n"),
        encoding="utf-8",
    )
    with pytest.raises(GitHostConfigError, match="default_branch_target"):
        load_git_host_config("demo", home=home)


def test_empty_default_branch_target_rejected(home):
    p = home / "projects" / "demo" / "git_hosts.yaml"
    p.write_text(
        YAML.replace("rules:\n", 'rules:\n  default_branch_target: ""\n'),
        encoding="utf-8",
    )
    with pytest.raises(GitHostConfigError, match="default_branch_target"):
        load_git_host_config("demo", home=home)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py -q`
Expected: FAIL，报 `AttributeError: 'GitHostConfig' object has no attribute 'default_branch_target'` 或非法值未抛 `GitHostConfigError`。

- [ ] **Step 3: Implement the config field**

在 `runtime/git_host/config.py`：

1. 在 `HOST_KINDS` 下方增加：

```python
BRANCH_TARGETS = ("dev", "test", "prod")
```

2. 给 `GitHostConfig` 末尾增加字段（保持现有默认字段顺序）：

```python
    default_branch_target: str = "test"
```

3. 在 `load_git_host_config` 里 `rules = data.get("rules") or {}` 之后解析并校验：

```python
    raw_target = rules.get("default_branch_target", "test")
    default_target = "test" if raw_target is None else str(raw_target).strip()
    if default_target not in BRANCH_TARGETS:
        raise GitHostConfigError(
            "rules.default_branch_target 只能是 "
            f"{'、'.join(BRANCH_TARGETS)}：{default_target!r}"
        )
```

4. 在 `return GitHostConfig(...)` 里带上 `default_branch_target=default_target`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py -q`
Expected: PASS。

- [ ] **Step 5: Bump version and verify manifests**

本次改动运行行为，按 `CONTRIBUTING.md` 在第一个运行时代码提交里升版本：

```bash
.venv/Scripts/python.exe scripts/bump_version.py 2.9.0
.venv/Scripts/python.exe -m pytest tests/test_version_sync.py -q
```

Expected: 版本同步测试 PASS，三个清单均为 `2.9.0`。

- [ ] **Step 6: Commit**

```bash
git add runtime/git_host/config.py tests/test_git_host_config.py .claude-plugin/plugin.json .codex-plugin/plugin.json .cursor-plugin/plugin.json
git commit -m "feat: git 配置支持 default_branch_target 并升版本至 2.9.0" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: CLI 省略 `--target` 时使用配置

**Files:**
- Modify: `scripts/git_host.py:60-64`（`branch create` 参数）、`scripts/git_host.py:139-142`（`branch` 分支处理）
- Modify: `skills/git-workflow/SKILL.md:14`、`skills/git-workflow/SKILL.md:132-138`
- Modify: `docs/usage.md:553-575`
- Test: `tests/test_git_host_cli.py`、`tests/test_skills.py`

**Interfaces:**
- Consumes: `GitHostConfig.default_branch_target`（Task 1）
- Produces: `branch create` 的 `--target` 变为可选；省略时使用配置值

- [ ] **Step 1: Write the failing tests**

在 `tests/test_git_host_cli.py` 的 `test_branch_create_calls_repo` 之后追加：

```python
def test_branch_create_defaults_to_test(repo, capsys):
    rc = _run(["branch", "create", "--name", "feature/test/lsh/1-x"], repo)
    assert rc == 0
    assert ("create_branch", "feature/test/lsh/1-x", "test") in repo.calls


def _set_default_branch_target(project_config, value):
    path = project_config / "git_hosts.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "rules:\n  forbid_commit_paths: [pom.xml]\n",
            f"rules:\n  default_branch_target: {value}\n  forbid_commit_paths: [pom.xml]\n",
        ),
        encoding="utf-8",
    )


def test_branch_create_uses_configured_target(repo, project_config, capsys):
    _set_default_branch_target(project_config, "dev")
    rc = _run(["branch", "create", "--name", "feature/dev/lsh/1-x"], repo)
    assert rc == 0
    assert ("create_branch", "feature/dev/lsh/1-x", "dev") in repo.calls


def test_branch_create_explicit_target_overrides_config(repo, project_config, capsys):
    _set_default_branch_target(project_config, "dev")
    rc = _run(
        ["branch", "create", "--name", "feature/test/lsh/1-x", "--target", "test"],
        repo,
    )
    assert rc == 0
    assert ("create_branch", "feature/test/lsh/1-x", "test") in repo.calls
```

在 `tests/test_skills.py` 末尾追加：

```python
def test_git_skill_branch_baseline_is_configurable():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "default_branch_target" in text
    assert "origin/test" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_cli.py tests/test_skills.py -q`
Expected: CLI 测试因 `--target` 必填而失败（argparse 退出 2）；技能测试因文案缺 `default_branch_target` 失败。

- [ ] **Step 3: Implement CLI and docs**

`scripts/git_host.py`：

1. 在 `from runtime.git_host.config import (...)` 的导入列表里加入 `BRANCH_TARGETS`。
2. 把 `bc.add_argument("--target", required=True)` 改为：

```python
    bc.add_argument("--target", choices=list(BRANCH_TARGETS))
```

3. 把 `branch` 分支处理改为：

```python
        if args.cmd == "branch":
            target = args.target or cfg.default_branch_target
            repo.create_branch(args.name, target)
            print(f"已从 origin/{target} 切出 {args.name}")
            return EXIT_OK
```

`skills/git-workflow/SKILL.md`：

1. 第 14 行改为：

```markdown
- 建任务 / 缺陷分支（默认基线取 `git_hosts.yaml` 的 `rules.default_branch_target`，未配置按 `origin/test`，例外见「从哪里切分支」）
```

2. 「从哪里切分支」第一条改为：

```markdown
- **默认取 `git_hosts.yaml` 的 `rules.default_branch_target`**（`dev` / `test` / `prod`，未配置时为 `test`）：新任务、缺陷修复、迭代需求以该分支最新基线为准
```

3. 该节末尾一句「从 test 基线切出的分支若要合入 dev」改为「从配置基线切出的分支若要合入 dev」，其余不变。

`docs/usage.md` 的 `git_hosts.yaml` 示例 `rules:` 下补一行：

```yaml
rules:
  default_branch_target: test   # 新分支默认基线：dev | test | prod
  forbid_commit_paths:        # 本地环境配置不提交
    - pom.xml
    - vite.config.ts
```

并在命令示例后补一句说明：

```markdown
`branch create` 省略 `--target` 时使用 `rules.default_branch_target`，未配置按 `test`。
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_cli.py tests/test_skills.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/git_host.py skills/git-workflow/SKILL.md docs/usage.md tests/test_git_host_cli.py tests/test_skills.py
git commit -m "feat: 分支默认基线由 git_hosts.yaml 配置" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 全量验证

**Files:** 无新增或修改；只运行检查。

- [ ] **Step 1: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 全部 PASS，无失败。

- [ ] **Step 2: Run the secrets check**

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`
Expected: 通过，无敏感信息命中。

- [ ] **Step 3: Confirm the working tree is clean**

Run: `git status --short`
Expected: 无输出（`.idea/` 已被忽略）。
