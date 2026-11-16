# 分支默认基线可配置设计（短）

**日期**：2026-11-16
**状态**：已确认
**类型**：小改动

## 问题

`git-workflow` 技能把新任务、缺陷修复、迭代需求的默认切分支基线写死为 `origin/test`。不同项目的集成分支不同，有的团队以 `dev` 为基线，每次都要靠用户临时说明，容易漏掉。

## 方案

在项目级 `git_hosts.yaml` 增加可选配置：

```yaml
rules:
  default_branch_target: test   # dev | test | prod；省略时为 test
```

- `runtime/git_host/config.py`：`GitHostConfig` 增加 `default_branch_target`，读取并校验；非法值报配置错误。
- `scripts/git_host.py`：`branch create --target` 改为可选，省略时取配置值；显式传入仍优先。
- `skills/git-workflow/SKILL.md`：默认基线改为「取该配置，未配置按 test」；用户明确要求「只进 dev」和线上热修的例外保持不变。
- `docs/usage.md`：配置示例补充该项。
- 测试覆盖：默认值、非法值、CLI 省略 `--target`、显式值覆盖配置。

## 不做

- 不改分支命名规则、`sync`、`merge` 的现有行为。
- 不做个人级覆盖：基线属于项目工作流事实，同一项目应统一。

## 兼容

未配置 `default_branch_target` 时行为与现在完全一致（从 `origin/test` 切）。
