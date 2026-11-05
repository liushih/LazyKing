---
name: git-workflow
description: >-
  代码托管操作：提交、推送、拉取、合并、建 MR/PR、开分支、热修同步。用户说「提交一下」「推到 dev」
  「开个 MR」「建分支」「同步热修」时使用。合并到 test 或 prod 只能建 MR，不能直接合并。写操作前必须回显并等待确认。
---

# Git 托管操作

## 适用场景

- 提交、推送改动（提交信息须符合团队格式）
- 建任务 / 缺陷分支（默认从 `origin/test` 切，例外见「从哪里切分支」）
- 发 MR 前把目标分支最新内容同步进当前分支（`sync`），冲突在本地解决
- 合并到 dev（以 origin/dev 为准本地合并，合并前核对将带入的内容，dev 可直接推送）
- 建 MR/PR 到 test、prod、dev（支持 GitHub、Gitee、GitLab）
- 热修复同步：把 prod 的热修复同步到 test 衍生分支，再合到 test 和 dev

不适用：

- 造数、查库 → 用 `data-gen-core` 或 `db-access`
- 只看提交历史、不改仓库 → 直接用 `git log`

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet。若提示有新版本：问用户「发现新版本，是否现在更新？」；用户确认后运行 <TOOLS_DIR>/update.ps1，完成后提醒用户检查 git status 并提交 data-tools/、生成的技能入口和 .gitignore；用户拒绝则继续，本次会话不再追问。脚本不存在、无新版本、检查失败或 update_check 关闭时继续。

## 前置检查

0. 运行 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> check --capability git`。有缺失时用 `project-setup` 补齐；不现场猜个人值，不修改共享 yaml；密钥只提示用户在自己的终端运行 `set-secret`。

1. 读 `<数据目录>/projects/<项目ID>/git_hosts.yaml`
2. 若共享 `git_hosts.yaml` 的 `user_tag` 用 `${USER_TAG}` 且 `personal.yaml` 缺值：走 `project-setup` 补齐。`set-user-tag` 只写 `personal.yaml`，不再修改共享文件；共享文件仍是字面值时保持旧行为并提示迁移。
3. 确认项目 ID；无法确定就问，不猜
4. 确认目标：dev、test 还是 prod

任一项缺失就停止，说明缺什么。

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`：从当前目录向上查找；找不到再读 `DATA_TOOLS_DIR`，再找不到读 `~/.data-tools/config.yaml` 的 `tools_dir`；仍找不到就问用户业务仓库根目录，不要猜。`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`：先读 `DATA_TOOLS_HOME`，没有再从当前目录向上查找，最后回退 `~/.data-tools`。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）；没有 venv 时用 `py -3.11` / `py -3` / `python` / `python3`，要求 3.11+；有 Python 但没 venv 时运行 `<TOOLS_DIR>/bootstrap.ps1`。

## 执行

所有操作通过命令行入口 `git_host.py`：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> commit -m "feat-<任务号>: <描述>\n\n<正文>"
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> push --branch <分支>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> sync [--from <test|dev|prod>]
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> mr create --from <源分支> --to <目标> --title "<标题>"
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> branch create --name <分支名> --target <dev|test|prod>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> merge --from <源分支> --to dev [--confirm-bring-in]
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> verify-flow --prod-branch prod --test-branch <test衍生分支> --target dev
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/git_host.py" --project <项目ID> hotfix sync --fix-branch <热修分支> --task <任务号>
```

### 写操作前必须回显并等待确认

推送、建 MR、合并、`sync`、热修同步都会改动仓库或影响他人可见的内容。执行前先回显：

- 平台、项目、源分支、目标分支
- MR 标题（如有）
- 将带入的提交数与文件数（合并到 dev 时，用 `verify-flow` 或 `merge` 的预检得到）

**只有用户明确说「确认」或「执行」，才运行写命令。** 不得因为用户只说了「推到 dev」就直接执行。

只读命令（`verify-flow`、`mr status`）可以直接执行。

## 硬规则

以下规则由工具强制执行。被拒绝时，**原样告诉用户规则名与原因**，不绕过、不换个方式硬做：

| 规则 | 说明 |
|---|---|
| `direct-merge` | 合到 test、prod 只能建 MR：`mr create --to test` 或 `--to prod` |
| `prod-derived` | prod 衍生分支不能直接合到 test 或 dev，要先经过 test 衍生的同步分支 |
| `net-increment` | 合到 dev 时若带入了非本分支的内容，先列清单，用户确认后加 `--confirm-bring-in` |
| `branch-naming` | 分支名须为 `feature/<目标>/<用户标识>/<任务号>-<描述>` |
| `commit-message` | 提交首行须为 `feat-<任务号>: <描述>` 或 `fix-<任务号>: <描述>`，且必须有正文 |
| `forbidden-path` | 本地环境配置（如 `pom.xml`、`vite.config.ts`）不得提交 |
| `push-target` | 本地分支名为 test、prod 时不得推送（只能走 MR）；dev 允许直接推送；其余分支只推到同名远端分支 |
| `sync-source` | `sync` 只能同步分支名「目标」对应的 origin 分支（`feature/test/...` 只同步 test），不能把 dev 并进送测分支 |

### 标准提交流程

1. `commit`（工作区已跟踪文件须干净；未跟踪文件不影响）
2. **若同时要进 dev，先于第 3 步**：`merge --to dev`，再 `push --branch dev`。`merge` 会先 fetch，以 `origin/dev` 为准预检；本地 dev 落后会先快进，已分叉则停止，不强行覆盖。先合 dev 再 `sync` test，避免把送测期间新增的改动一并带入 dev
3. **若要进 test**：`sync` 把最新 `origin/test` 合进当前分支；无冲突才继续，有冲突按下文「冲突处理」解决后再继续
4. `push` 推到同名远端分支，再 `mr create --to test`，此时 MR 不会有冲突

### 冲突处理

`sync`、`merge` 遇冲突会**保留现场**并列出冲突文件，工具自己不会解决，也不会 abort。解决冲突时：

1. **禁止整文件取一边**：不用 `checkout --ours/--theirs`、`-X ours/theirs`
2. **两边意图都保留**：逐个冲突块判断，合并双方改动，不得删掉任一方的逻辑，不得为了消除冲突而阉割功能
3. **先给用户看再提交**：用 `git diff`（合并提交用 `git show --cc`）列出动过的冲突块，说明每处怎么合，用户确认后才 `git add <文件>` 与 `git commit --no-edit`
4. **解决后验证**：有测试就跑，没有至少做编译或语法检查，通过后才推送
5. **拿不准就停**：两边逻辑互斥、无法同时保留时，不替用户选，列出两种写法让用户决定
6. 用户要放弃：`git merge --abort`

### 从哪里切分支

- **默认从 `origin/test` 切**：新任务、缺陷修复、迭代需求一律以 `origin/test` 最新基线为准
- 仅当用户明确要求「只进 dev、不经 test」时，从 `origin/dev` 切
- 线上热修复从 `origin/prod` 切

从 test 基线切出的分支若要合入 dev，按 `net-increment` 预检：先列出将带入 `origin/dev` 的非本分支提交，用户确认后才加 `--confirm-bring-in`，不得未经确认把 test 内容带进 dev。

### 热修复流程

1. 从 `origin/prod` 切热修复分支，修复，提交
2. 热修复分支开 MR 到 prod
3. 从 `origin/test` 切同步分支，执行 `hotfix sync`（用 cherry-pick 搬热修复的提交，不合并热修复分支本身）
4. 同步分支开 MR 到 test
5. 同步分支合到 dev 前，用 `verify-flow` 核对，确认只带入热修复的改动

## 令牌

- 令牌只从项目 `.env` 读取，`git_hosts.yaml` 的 `token_key` 指定键名
- 令牌缺失时只报键名（如 `GITLAB_TOKEN_XXX`），由用户自己去 `.env` 里填
- 不要让用户把令牌贴进对话。如果用户已经贴进来，提醒他去吊销并换一个
- 不要在任何命令行参数、日志、报告中输出令牌

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺 `git_hosts.yaml` | 报路径，引导补配置，不现场猜仓库与平台 |
| 缺令牌 | 报键名，引导用户在项目 `.env` 中填写，不要求粘贴 |
| 令牌无效（401/403） | 报「令牌无效或权限不足」，不重试 |
| 平台返回 409 或 422（MR 已存在） | 报告已有编号和链接，**不重复创建** |
| 网络不通 | 报错并提示检查代理，不静默重试写请求 |
| `sync` / `merge` 冲突 | 现场保留，列出冲突文件；按「冲突处理」保留双方改动解决，不得取一边 |
| cherry-pick 冲突 | 工具已中止并列出冲突文件，不尝试自动解决；由用户处理后重新开始 |
| 规则拒绝 | 原样告诉用户规则名与原因，不绕过 |
