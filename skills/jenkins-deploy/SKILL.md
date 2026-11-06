---
name: jenkins-deploy
description: >-
  Jenkins 发版：根据当前需求的改动推断要构建的模块，经用户确认后触发对应 Jenkins 任务并回报结果。
  用户说「发版」「构建一下」「部署到 dev/test」「把这个需求的模块发了」「Jenkins」时使用。
  首次使用先问地址和账号并保存 token。触发前必须回显并等待确认；没有权限就提示，不绕过。
---

# Jenkins 发版

## 适用场景

- 发版当前需求涉及的模块：按分支改动推断模块，回显确认后触发构建
- 用户直接指定模块或环境（「发 order-service 到 test」）
- 首次接入 Jenkins：保存地址、账号、token，并生成「模块 → 任务」映射
- 查某次构建的状态

不适用：

- 提交、推送、建 MR → 用 `git-workflow`
- 创建、修改 Jenkins 任务本身 → 不支持，请在 Jenkins 页面操作

## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；再找不到读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet。若提示有新版本：问用户「发现新版本，是否现在更新？」；用户确认后运行 <TOOLS_DIR>/update.ps1。data-tools/、.data-tools/ 和生成的技能入口只在本机使用，按策略不提交进业务仓库；不要提醒用户提交这些改动。用户拒绝则继续，本次会话不再追问。脚本不存在、无新版本、检查失败或 update_check 关闭时继续。

## 前置检查

0. 运行 `"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/config.py" --project <项目ID> check --capability jenkins`。有缺失时用 `project-setup` 补齐；不现场猜个人值，不修改共享 yaml；密钥只提示用户在自己的终端运行 `set-secret`。

1. 确认项目 ID；无法确定就问，不猜。
2. 读共享 `jenkins.yaml`。共享文件缺失 = 维护人任务；`JENKINS_USER` 或 `JENKINS_TOKEN` 缺失 = 用 `project-setup`，token 只让用户在自己的终端运行 `set-secret`。
3. 确认目标环境（dev、test 等，取自 `jenkins.yaml` 里模块的 `jobs` 键）。用户没说就问，不猜。

### 首次流程

1. 问 Jenkins 地址。
2. 账号：用 `git config user.name` 或 `git_hosts.yaml` 的 `user_tag` 作候选，问「账号是 xxx 吗」。
3. 请用户在自己的终端运行 `set-secret JENKINS_TOKEN`（或直接编辑项目 `.env`），建议使用单独生成、可随时吊销的 API token。不要把 token 贴进对话。
4. 确认 `.env` 已有 token 后运行 `setup`；`setup` 在 stdin 为空时会复用 `.env` 里的 token。不要把 token 放进命令行参数；之后的回复、总结、日志里都不回显、不复述 token。
5. `setup` 成功后运行 `discover` 列出任务和参数，与用户核对，按目录 → 模块 → 任务的对应关系写 `jenkins.yaml` 的 `modules`（格式见 `skills/_TEMPLATE/jenkins.example.yaml`）。
6. 写完 `jenkins.yaml` 后只留本机，不暂存、不提交。`data-tools/` 与 `.data-tools/` 按策略整体不进业务仓库 git；需要团队共享时通过内网制品库或共享目录分发。`.env` 里的 token 不要写进任何会提交的文件。

## 路径

命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`，`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`，解析顺序见第 0 步；不要写死本机绝对路径。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）。

## 执行

所有操作通过命令行入口 `jenkins.py`：

```bash
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> setup --base-url <地址> --user <账号>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> discover --filter <关键字>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> modules --repo <业务仓库根目录>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> build --env <环境> --dry-run
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> build --env <环境> --module <模块> --branch <分支>
"<TOOLS_DIR>/.venv/Scripts/python.exe" "<TOOLS_DIR>/scripts/jenkins.py" --project <项目ID> status --job <任务名> --number <构建号>
```

PowerShell 里同样直接运行这两条命令；`setup` 会从 `.env` 读取已保存的 token，不再通过命令行参数或对话传递。执行后不要在任何回复里引用 token。

`build` 的可选参数：

- `--module <模块>` 可重复；不写则按改动推断
- `--branch <分支>` 不写则取当前分支
- `--sequential`：前一个成功才触发下一个，失败即停；默认是全部进 Jenkins 队列，实际先后由 Jenkins 决定
- `--no-wait`：只触发，输出队列地址
- `--dry-run`：只回显将要触发的任务和参数

### 排队冲突处理

触发前会先查同一任务在 Jenkins 队列里排队中的项和正在运行的构建：

- 参数与本轮相同（任务本身没有参数时，同任务的在途构建都算相同）：先取消排队项或停止正在运行的构建，再触发新的，输出 `[取消]`；取消失败输出 `[取消失败]` 并照常触发。
- 参数不同：不动对方的构建，本次构建正常入队。
- 自己的构建被别人取消排队项或停止时，自动接管同任务、同参数的新构建继续等结果，输出 `[接管]`，最终按那个构建的结果汇报；找不到替代构建时才按取消 / ABORTED 报失败。
- `--dry-run` 会把这些将取消的构建以 `[将取消]` 一并回显，确认时一并告知用户。
- 读取排队状态失败只提示，不阻断发版。

### 推断模块

先运行 `modules`：

- 有「未映射文件」时列给用户，问它们属于哪个模块，不猜。
- 有「未提交的改动」时告诉用户这些改动不会被构建（Jenkins 构建远端代码，推断也不计入），问先提交推送还是继续。
- 「未推送提交」不是 0，或显示「远端无该分支」：提醒用户 Jenkins 构建的是远端代码，问先推送还是继续。推送交给 `git-workflow`。

### 写操作前必须回显并等待确认

触发构建会影响他人可见的环境。执行前先用 `build --dry-run` 得到并回显：

- Jenkins 地址、分支、环境
- 模块 → 任务名、构建参数

**只有用户明确说「确认」或「执行」，才运行不带 `--dry-run` 的 `build`。** 不得因为用户只说了「发版」就直接触发。

`modules`、`discover`、`status`、`--dry-run` 是只读命令，可以直接执行。

### 汇报

逐个模块汇报结果和链接。失败的构建附上命令输出里的控制台末尾，帮用户判断原因；不要自行重新触发。输出里有 `[取消]`、`[取消失败]` 或 `[接管]` 时，一并告诉用户取消了哪个任务的在途构建、或改跟了哪个构建，原因是什么。

## 失败处理

| 情况 | 动作 |
|---|---|
| 缺 `jenkins.yaml` 或缺 token | 走首次流程，缺 token 时只报键名 `JENKINS_TOKEN` |
| 401 | 报「账号或 token 无效」，引导重新提供，不重试 |
| 403 | 报「当前账号无权构建 <任务名>」，提示联系管理员，不重试、不换方式绕过 |
| 404 | 报任务不存在，建议重跑 `discover` 更新映射 |
| 预检失败（缺环境任务、参数名对不上） | 原样报缺少或多余的名字，整体一个都不触发；修正 `jenkins.yaml` 后重来 |
| 网络不通或超时 | 报错；**不自动重试触发**（可能重复构建），由用户决定是否重发 |
| 读取排队状态失败 | 提示原因后照常触发，不阻断发版 |
| 取消重复构建失败（无权限等） | 报原因并照常触发；本次构建可能排在对方之后 |
| 排队被取消、ABORTED、UNSTABLE | 有同任务同参数的替代构建时先接管（见「排队冲突处理」）；没有才原样报状态和链接 |
| 等待超时 | 报超时和构建链接，构建本身不会被取消 |
