---
name: project-setup
description: >-
  初始化个人配置：检查共享配置还缺哪些个人值，问清楚后写入 personal.yaml 与 .env。
  用户说「初始化个人配置」「新同事接入」「配置我的账号」「配一下环境」「个人配置」时使用。
  不现场猜个人值，不修改共享 yaml，密钥只让用户在自己的终端输入。
---

# 个人配置初始化

## 适用场景

- 新同事第一次使用工具包
- 换了机器或重新 clone 了业务仓库
- 某个能力提示缺少个人配置
- 团队共享流程新增了变量，需要补自己的值

不适用：

- 团队共享配置缺失（如没有 `jenkins.yaml`、`adapter.yaml`）→ 交维护人，或用对应技能的首次接入流程
- 造数、查库、Git、报告、浏览器测试的日常操作 → 用对应技能

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet。若提示有新版本：问用户「发现新版本，是否现在更新？」；用户确认后运行 <TOOLS_DIR>/update.ps1，完成后提醒用户检查 git status 并提交 data-tools/、生成的技能入口和 .gitignore；用户拒绝则继续，本次会话不再追问。脚本不存在、无新版本、检查失败或 update_check 关闭时继续。

## 前置检查

1. 确认项目 ID；无法确定就问，不猜。
2. 运行 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> check --json`，按能力分组得到缺失与漂移。
3. 询问用户需要哪些能力：造数、查库、Git、Jenkins、报告、浏览器测试。只配置选中的能力。

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`，`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`，解析顺序见第 0 步；不要写死本机绝对路径。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）。

## 执行

1. 对每个选中的能力，只处理它的 `missing` 项；不要给未选中的能力填值。
2. 非敏感值按 `description` 和 `default_from` 给默认值并请用户确认：
   - `git_user_name`：`git config user.name`
   - `repo_root`：`<TOOLS_DIR>` 的上一级
   - `user_tag`：已配置的 `USER_TAG`
   - `none`：直接问
3. 用 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> set KEY=值` 写入 `personal.yaml`；一次可写多个键。
4. 密钥不在对话中索要。打印一条让用户在自己的终端运行的命令：`"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> set-secret <KEY>`。用户运行后只检查键是否存在，不读取值、不回显值。
5. 重新运行 `check --capability <能力>`，直到选中能力为 `ok` 或用户明确跳过。
6. 可选只读验证：`jenkins.py modules`、`browser.py doctor`、`git_host.py verify-flow`。默认不做，询问用户后再跑；失败只报告，不自动修。
7. 汇总写入的文件、仍缺的键、后续命令。说明 `personal.yaml` 与 `.env` 已被 gitignore，共享 yaml 未被修改。

## 失败处理

| 情况 | 动作 |
|---|---|
| 共享配置缺失（如没有 `jenkins.yaml`） | 说明这是团队维护人任务，不在 setup 中现场创建；需要时走对应技能的首次接入流程 |
| 共享配置含未声明变量 | 报文件与键名，停下，请维护人补 example；不猜 |
| 用户不知道某个值 | 保留缺失，说明该能力暂不可用；不填占位值 |
| 用户拒绝提供密钥 | 说明对应能力不可用，继续配置其他能力 |
| `check` 仍报漂移 | 列出文件与建议，交给维护人处理 |
| 令牌已贴进对话 | 提醒用户去吊销并换一个；后续只让用户在终端输入 |
