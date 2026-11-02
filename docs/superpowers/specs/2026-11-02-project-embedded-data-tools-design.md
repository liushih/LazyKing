# 业务项目整包内置 data-tools 设计

**日期**：2026-11-02
**状态**：待审阅
**关联**：`scripts/sync_project.py`、`bootstrap.ps1`、`runtime/config.py`、`skills/*/SKILL.md`

## 1. 背景与目标

claudeTool 目前的 5 项能力（`db-access`、`data-gen-core`、`adapter-bootstrap`、`report-writer`、`git-workflow`）以本机全局安装为主：技能规则通过插件或 `install.ps1` 分发，运行时依赖本机 clone 的 claudeTool 和 `.venv`，业务适配层（`adapter.yaml`、`pitfalls.md`）放在 `~/.data-tools`，只属于个人。

目标是让业务项目自身携带这套能力：同事 clone 业务仓库后，只需本机有 Python 3.11+，按一次 bootstrap、填一次 `.env`，就能用同样的白话方式使用全部 5 项能力；业务规则、坑库随仓库共享。

成功标准：

- 同事不需要单独 clone claudeTool，也不需要理解 `<TOOLS_DIR>`。
- 机器没有 Python 时，得到明确的下载安装指引，而不是 Python 报错堆栈。
- 5 项能力全部按同一套项目内路径解析和环境检查工作。
- 业务规则和坑库随业务仓库共享，凭据、台账、报告产物不进仓库。
- 同步工具可重复执行，升级不丢业务数据。

## 2. 决策：整包内置

对比过两种形态：

- **项目级规则文件**：业务仓库只放 `.claude/skills` 等规则，运行时仍指向各自本机 clone 的 claudeTool。仓库轻，但同事仍需第二个仓库，`adapter.yaml`、`pitfalls.md` 不共享。
- **整包内置**：业务仓库提交 `data-tools/`（约 474KB 源码）和 `.data-tools/` 的共享部分。同事一个仓库即可用。

选择整包内置，因为需求是「让同事使用」，而业务适配层和坑库是能力的一部分；只同步规则不解决同事首次接入的问题。代价是每个业务仓库一份副本，需要用同步工具控制漂移。

## 3. 范围

**做**

- 业务仓库内的 `data-tools/` 工具包、`.data-tools/` 数据根。
- 一键 bootstrap：Python 检测、venv、依赖安装。
- 5 个技能的项目内路径解析与「第 0 步」环境检查。
- 同步/升级工具：复制、渲染、写 VERSION、更新 `.gitignore`、保留业务数据。
- 文档与测试。

**不做**

- Java 等其它语言适配。
- 自动下载或静默安装 Python。
- 改写 5 项能力的业务逻辑。
- 删除现有插件市场、`setup.ps1`、`install.ps1 -Scope project`；它们继续服务个人/全局场景。
- Mac/Linux 的 bootstrap 脚本。技能内的解释器路径兼容 POSIX，但本期只提供 PowerShell bootstrap。
- 禅道、报告、Git 托管之外的新的业务能力。

## 4. 业务仓库目录布局

```text
<业务仓库>/
├── data-tools/                        # 从 claudeTool 同步，提交
│   ├── skills/                        # 规则源（含 _references、_TEMPLATE）
│   ├── runtime/
│   ├── scripts/
│   ├── requirements.txt
│   ├── bootstrap.ps1                  # 首次接入与环境检查
│   ├── update.ps1                     # 版本检查与一键更新
│   ├── VERSION                        # 版本 + 源 commit + 同步时间
│   ├── README.md                      # 同事接入说明
│   ├── LICENSE
│   └── .venv/                         # 本机生成，不提交
├── .data-tools/                       # 项目数据根
│   ├── config.yaml                    # 提交：default_project
│   ├── projects/<项目ID>/
│   │   ├── adapter.yaml               # 提交：团队共享业务规则
│   │   ├── pitfalls.md                # 提交：团队共享坑库
│   │   ├── report.yaml                # 提交（可选）
│   │   ├── git_hosts.yaml             # 提交（可选，只含 token 键名）
│   │   ├── scripts/                   # 提交：impl 步骤代码
│   │   ├── .env.example               # 提交：键名模板
│   │   └── .env                       # 不提交：各人凭据
│   ├── templates/<项目ID>/            # 提交（可选）
│   └── reports/                       # 不提交：报告产物
├── .claude/skills/<5个技能>/SKILL.md  # 提交：生成物
├── .cursor/rules/*.mdc                # 可选，提交
├── AGENTS.md                          # 可选，提交
└── .gitignore                         # 追加 data-tools 忽略块
```

关键取舍：

- `data-tools/` 提交：同事 pull 后规则和运行时都在，不依赖第二次 clone。
- `.data-tools/` 部分提交：`adapter.yaml`、`pitfalls.md` 这类团队知识进仓库；`.env`、`ledger.csv`、`reports/` 不进。
- 生成物也提交：`.claude/skills` 等随仓库走，打开即用；同步工具负责重新生成，不手改。
- 默认只生成 Claude 的技能，Cursor/Codex/DSH 通过 `--targets` 按需追加，避免同一套规则提交三份。

## 5. 同事接入流程

```text
1. git clone <业务仓库>
2. 在仓库根目录运行：
   powershell -ExecutionPolicy Bypass -File data-tools/bootstrap.ps1
3. 脚本检查 Python 3.11+
   - 没有：打印下载地址，退出，不创建任何东西
   - 有：创建 data-tools/.venv，安装 requirements.txt
4. 复制 .data-tools/projects/<项目ID>/.env.example 为 .env，填账号
5. 打开 Claude Code / Cursor / Codex / DSH，直接说：
   「在 dev 造 100 张提货单」
```

第一次使用时，技能前置检查会再次确认环境和 venv；如果同事跳过了 bootstrap，技能会提示先运行它。

后续技能启动时会顺带检查版本：发现 `data-tools` 落后时只提示，不自动更新；同事运行 `data-tools/update.ps1` 即可更新，不需要先 pull 业务仓库。

## 6. Python 检查

### 6.1 bootstrap.ps1（接入时）

- 位置：claudeTool 仓库根，同步时复制到 `<业务仓库>/data-tools/bootstrap.ps1`。
- 工具目录取 `$PSScriptRoot`，项目根取 `Split-Path $PSScriptRoot -Parent`。
- 检测顺序：
  1. `<tools>/.venv/Scripts/python.exe`
  2. `py -3.11`
  3. `py -3`
  4. `python`
  5. `python3`
- 版本要求 `>= 3.11`；低于版本按「未安装」处理。
- `py -3` 可能指向旧版本，必须解析 `--version` 输出后再判断。
- 捕获 stderr，兼容部分 Python 把版本写到 stderr 的情况。
- 缺失或版本过低时输出：

```text
[data-tools] 未检测到 Python 3.11+。
请到 https://www.python.org/downloads/ 下载安装，
安装时勾选 "Add python.exe to PATH"，装好后重新运行本脚本。
```

- 不自动下载、不调用安装器、不修改系统 PATH。
- 参数：
  - `-ProjectId <ID>`：可选，创建 `.data-tools/projects/<ID>/` 骨架。
  - `-CheckOnly`：只检查，不创建 venv。
- `-CheckOnly` 退出码：

| 退出码 | 含义 |
|---|---|
| 0 | Python 3.11+ 且 `.venv` 已存在 |
| 1 | 未检测到 Python 3.11+ |
| 2 | Python 可用，但 `.venv` 不存在 |

- 正常模式（不带 `-CheckOnly`）：Python 可用时创建 `.venv`、升级 pip、安装 `requirements.txt`，成功后退出 0；Python 不可用时退出 1。
- 幂等：`.venv` 已存在时只补装依赖，不重建。

### 6.2 技能「第 0 步」（日常使用时）

5 个 `SKILL.md` 都插入同一段环境前置：

```markdown
## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；仍找不到再读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet：有新版本就把提示原样告诉用户，不自动更新；脚本不存在、无新版本或检查失败则继续。
```

这段放在 `db-access`、`data-gen-core`、`adapter-bootstrap`、`report-writer`、`git-workflow` 五个技能里，保证「所有能力」都生效。原有 `## 前置检查` 段保留，第 0 步放在最前面。详细说明放在 `skills/_references/project-layout.md`，技能里保留上面的可执行摘要。

## 7. 路径解析

数据路径目前全部收敛在 [runtime/config.py](../../../runtime/config.py) 的 `data_home()`，改这一处即可覆盖所有脚本：

```python
def data_home() -> Path:
    env = os.getenv("DATA_TOOLS_HOME")
    if env:
        return Path(env)
    current = Path.cwd().resolve()
    for parent in (current, *current.parents):
        candidate = parent / ".data-tools"
        if candidate.is_dir():
            return candidate
    return Path.home() / ".data-tools"
```

优先级：**显式环境变量 > 项目内 `.data-tools/` > 用户目录 `~/.data-tools`**。

现有测试都显式设了 `DATA_TOOLS_HOME`，行为不变；新增测试覆盖项目内查找。`runtime/report_config.py`、`runtime/git_host/config.py`、`scripts/collect.py` 已经统一走 `config.data_home()` / `config.project_dir()`，不需要各自改。

`<TOOLS_DIR>` 不写死绝对路径。同步渲染时保留占位符，由技能按「项目根目录下的 `data-tools/`」解析。这样提交到 git 后换机器不会失效。

## 8. 同步与更新

新增 `scripts/sync_project.py`（在 claudeTool 里运行）：

```bash
python scripts/sync_project.py \
  --project-dir C:\project\<业务仓库> \
  --project-id <项目ID> \
  --targets claude
```

参数：

| 参数 | 说明 |
|---|---|
| `--project-dir` | 必填，业务仓库根目录 |
| `--project-id` | 可选，写入 `.data-tools/config.yaml` 的 `default_project` |
| `--targets` | 默认 `claude`；可选 `cursor`、`codex`、`dsh`，逗号分隔 |
| `--dry-run` | 只打印将要执行的动作，不写文件 |

执行步骤：

1. 校验 `--project-dir` 存在；不是 git 仓库时警告，但继续。
2. 复制白名单内容到 `<业务仓库>/data-tools/`：
   - `skills/`（含 `_references`、`_TEMPLATE`）
   - `runtime/`
   - `scripts/`（含 `sync_project.py`、`update.py`）
   - `requirements.txt`
   - `bootstrap.ps1`
   - `update.ps1`
   - `LICENSE`
   - 从 `skills/_TEMPLATE/project-readme.md` 渲染生成 `README.md`，写入项目 ID、bootstrap 命令、`.env` 位置和更新命令
   - 排除 `__pycache__`、`*.pyc`、`.venv`。
3. 写入 `<业务仓库>/data-tools/VERSION`：

```yaml
version: 1.4.0
source_commit: 1fb5862
synced_at: 2026-11-02T10:30:00+08:00
source: https://github.com/liushih/claudeTool.git
```

4. 渲染技能入口：
   - `claude`：`.claude/skills/<name>/SKILL.md`
   - `cursor`：`.cursor/rules/<name>.mdc`
   - `codex`：`AGENTS.md` 中的 `data-tools:begin` / `data-tools:end` 块
   - `dsh`：`.dsh/skills/<name>/SKILL.md`
   - 使用可移植渲染，保留 `<TOOLS_DIR>`，不替换成本机绝对路径。
5. 初始化数据目录：
   - 创建 `.data-tools/projects/<项目ID>/`（如果给了 `--project-id`）。
   - `.data-tools/config.yaml` 不存在时创建并写入 `default_project`；已存在时不覆盖，只在缺少 `default_project` 时补写。
   - 若 `.env.example` 不存在，写一个带注释的空模板；`adapter-bootstrap` 接入时按 `${VAR}` 补全键名。
   - **不覆盖**已有 `adapter.yaml`、`pitfalls.md`、`report.yaml`、`git_hosts.yaml`、`.env`。
6. 在 `.gitignore` 追加带标记的块；重复执行时先删旧块再追加：

```gitignore
# data-tools:begin
data-tools/.venv/
data-tools/**/__pycache__/
.data-tools/projects/*/.env
.data-tools/projects/*/ledger.csv
.data-tools/reports/
.data-tools/.update-check.json
.data-tools/**/*.log
# data-tools:end
```

7. 打印本次新增/更新/保留的文件，以及下一步命令。

维护者同步流程（pull 路径）：

1. claudeTool 更新后，重跑 `sync_project.py`。
2. 检查业务仓库 `git diff`，提交并推送。
3. 同事 pull；若 `requirements.txt` 有变化，同步工具提示「需重跑 bootstrap.ps1」。

同事不 pull 业务仓库时，走 8.1 的版本提示 + 一键更新。

同步工具只增改工具和生成物，不动 `.data-tools` 下的业务数据，保证可重复执行。`VERSION` 用于排查「同事那台机器为什么行为不一致」。

### 8.1 不拉业务仓库时的更新机制

`data-tools/` 是业务仓库里的副本，同事不 `git pull` 就不会自动变新。为了做到「不拉业务仓库也能及时更新」，增加版本提示 + 一键更新。

**版本来源**

- 默认源：`https://github.com/liushih/claudeTool.git`；`.data-tools/config.yaml` 不存在时使用默认源。
- 可在 `.data-tools/config.yaml` 覆盖为公司内网镜像或共享路径：

```yaml
data_tools:
  source: https://git.example.com/group/claudeTool.git
  update_check: true
  check_interval_hours: 24
```

**检查**

- `data-tools/update.ps1 -CheckOnly -Quiet` 由技能第 0 步调用，也可手动运行。

| 参数 | 说明 |
|---|---|
| `-CheckOnly` | 只检查，不更新；有新版本退出码 10 |
| `-Quiet` | 无新版本时不输出；有新版本仍打印提示 |

- 检查逻辑放在 `scripts/update.py`（Python，便于单元测试），`update.ps1` 只负责找解释器并转发。
- 版本比对：
  - 远端有 `vX.Y.Z` tag：取最高 tag 与本地 `VERSION.version` 比较。
  - 没有 tag：比较远端 `refs/heads/main` 的 commit 与本地 `VERSION.source_commit`，提示「远端有新提交」。
- 结果缓存到 `.data-tools/.update-check.json`，默认 24 小时内不重复联网。
- `git ls-remote` 设置短超时（例如 5 秒），失败按无更新处理。
- 网络失败或源不可达：不阻塞技能，按「无更新」处理，下次再试。
- 有新版本时输出一行：

```text
[data-tools] 本地 v1.4.0，远端 v1.5.0。运行 data-tools/update.ps1 更新。
```

- 退出码：`0` 无更新/检查失败；`10` 有新版本。技能看到 `10` 只提示，不自动执行更新。

**更新**

- `data-tools/update.ps1`（不带 `-CheckOnly`）：
  1. 读取源地址和当前 `VERSION`。
  2. 检查业务仓库 `data-tools/` 是否有未提交改动；有则拒绝，提示先提交或暂存。不是 git 仓库时跳过该检查并警告。
  3. 浅克隆源到临时目录，确认远端版本高于本地。
  4. 用临时目录里的 `scripts/sync_project.py` 覆盖 `data-tools/` 和技能入口，保留 `.data-tools/`。
  5. 清理临时目录，打印「已更新到 vX；请在业务仓库提交 data-tools/ 的变更」。
- 更新动作由临时目录里的脚本执行，避免覆盖正在运行的本地脚本。
- `update.ps1` 需要 Python；没有时按 bootstrap 的提示先安装 Python。
- 更新是显式动作，不静默替换代码；不自动 `git commit`、不自动 `git push`。
- 没有业务仓库提交权限的同事，可以保留本地改动继续用，或把 diff 交给维护人提交。
- 更新失败不影响当前版本继续使用。

**为什么不做静默自动更新**

- 避免在后台替换可执行代码。
- 避免无提示地弄脏业务仓库。
- 保留可复现性：提交进仓库的 `data-tools/` 才是团队认可的版本。

## 9. 安全与提交边界

**进仓库**

- `data-tools/` 全部源码。
- `.data-tools/projects/<项目ID>/adapter.yaml`：只含 `${VAR}` 占位符，不含凭据。
- `.data-tools/projects/<项目ID>/pitfalls.md`：踩坑记录，不含凭据。
- `.data-tools/projects/<项目ID>/report.yaml`、`git_hosts.yaml`：只含 `token_key` 键名，不含令牌。
- `.data-tools/projects/<项目ID>/scripts/`：业务 `impl` 代码。
- `.data-tools/templates/<项目ID>/`：报告模板。
- `.env.example`：键名模板，值为空。

**不进仓库**

- `.env`、`.env.*`（除 `.env.example`）。
- `ledger.csv`。
- `.data-tools/reports/`。
- `data-tools/.venv/`、`__pycache__/`、`*.pyc`。
- `*.log`。
- 令牌、密码、私钥。

`scripts/check_secrets.py` 随 `data-tools/scripts/` 一起分发；建议在业务仓库提交前运行一次。同步工具本身不读取 `.env`，只复制和渲染文件。

更新只从 `data_tools.source` 配置的地址拉取；不在后台执行远端脚本。`update.ps1` 更新的是 `data-tools/` 源码，不会读取或上传 `.env`。

## 10. 文件级改动

| 文件 | 改动 |
|---|---|
| `scripts/sync_project.py` | 新增：复制工具包、渲染技能、更新 `.gitignore`、写 `VERSION` |
| `scripts/update.py` | 新增：版本比对、检查缓存、检查/执行更新 |
| `update.ps1`（仓库根） | 新增：找解释器并转发 `update.py`，支持 `-CheckOnly` |
| `scripts/install.py` | 抽出渲染逻辑，新增 `portable=True` 保留 `<TOOLS_DIR>` |
| `bootstrap.ps1`（仓库根） | 新增：Python 版本检测、venv、依赖安装、`-CheckOnly` |
| `runtime/config.py` | `data_home()` 增加项目内 `.data-tools/` 向上查找 |
| `skills/_references/project-layout.md` | 新增：项目内路径、Python 检查、bootstrap 说明 |
| `skills/_TEMPLATE/project-readme.md` | 新增：业务仓库 `data-tools/README.md` 的模板 |
| 5 个 `skills/*/SKILL.md` | 增加「第 0 步：环境检查」；「路径」段改为项目内解析；`adapter-bootstrap` 额外维护 `.env.example` 键名 |
| `skills/_references/runtime-contract.md` | 补充项目内 `<TOOLS_DIR>` / `<DATA_HOME>` 语义 |
| `README.md`、`docs/usage.md` | 新增「团队项目接入（整包内置）」，保留个人插件安装方式 |
| `tests/test_sync_project.py` | 新增：复制、幂等、保留业务数据、`.gitignore` 块 |
| `tests/test_update.py` | 新增：版本比较、检查缓存、脏工作区拒绝、更新调用 |
| `tests/test_config.py` | 修改：新增项目内 `.data-tools/` 优先于 `~/.data-tools` 的用例 |
| `tests/test_install.py` | 修改：新增 `portable=True` 保留 `<TOOLS_DIR>` 的用例 |
| `tests/test_skills.py` | 修改：断言 5 个技能都包含「第 0 步：环境检查」 |

不改 5 项能力的核心执行逻辑，只动路径解析、环境前置和分发层。

## 11. 测试与验收

**自动化**

- `pytest`：
  - `data_home()` 在无环境变量时向上找到项目内 `.data-tools/`。
  - `data_home()` 在环境变量存在时仍优先使用环境变量。
  - `sync_project` 复制白名单文件，排除 `.venv` / `__pycache__`。
  - `sync_project` 重复执行不重复写 `.gitignore` 块。
  - `sync_project` 不覆盖已有 `adapter.yaml`、`pitfalls.md`、`.env`。
  - `portable=True` 渲染保留 `<TOOLS_DIR>`；非 portable 仍替换为绝对路径。
  - `update.py` 正确比较 tag 版本与 commit。
  - `update.py` 在缓存有效期内不联网。
  - `update.py` 在 `data-tools/` 有未提交改动时拒绝更新。
- 用临时目录模拟业务仓库，跑完 sync 后断言目录结构和 `.gitignore` 块。

**手工验收**

1. 没有 Python 的环境跑 `bootstrap.ps1`：看到下载提示，退出码 1，不产生 `.venv`。
2. 有 Python 的环境：bootstrap 成功，`.venv` 可用，退出码 0。
3. `.venv` 不存在但 Python 可用时，`bootstrap.ps1 -CheckOnly` 退出码 2。
4. 新业务仓库 sync 后，`.claude/skills` 下 5 个技能可见。
5. 从仓库子目录触发技能，`<TOOLS_DIR>` 和 `<DATA_HOME>` 仍能向上找到。
6. 填好 `.env` 后，说「造 1 张提货单」能走通。
7. 重跑 sync，业务数据不丢，`.gitignore` 不重复。
8. 远端版本变化后，技能提示有新版本；运行 `update.ps1` 更新成功，`.data-tools/` 数据不变。
9. `data-tools/` 有未提交改动时，`update.ps1` 拒绝并提示先提交/暂存。

## 12. 风险与取舍

| 风险 | 影响 | 应对 |
|---|---|---|
| 每个业务仓库一份副本，版本漂移 | 同事行为不一致 | `VERSION` 记录源 commit；升级跑 sync；CI 可校验版本 |
| 提交生成物产生 diff 噪音 | 升级提交变大 | 默认只生成 Claude；按需加 target |
| Windows 的 `python` 是 Microsoft Store 占位程序 | 检测误判或弹商店 | 优先 `py -3.11` / `py -3`，解析版本输出；失败再试 `python` |
| 同事从子目录启动 AI 工具 | 相对路径找不到 | 向上查找 `data-tools/` / `.data-tools/`；找不到就问，不猜 |
| `requirements.txt` 变更多，同事没重跑 bootstrap | 运行时报缺包 | sync 检测变化并提示；技能前置发现 venv 异常时提示重跑 |
| 业务仓库体积增大 | clone 变慢 | 只提交约 474KB 源码，`.venv` 不入库 |
| 共享 `adapter.yaml` 含内部地址 | 敏感信息进仓库 | 只提交 `${VAR}` 占位符；地址可放 `.env`，需要时改为 `${BASE_URL}` |
| 更新源不可达（内网/GitHub） | 检查失败，同事不知道有新版本 | 检查失败不阻塞；配置里可换内网镜像；提示只在成功时出现 |
| 更新时业务仓库有未提交改动 | 覆盖本地改动 | 更新前检查 `data-tools/` 工作区，脏则拒绝 |
| 同事没有业务仓库提交权限 | 更新后留下本地 diff | 允许本地继续用；把 diff 交给维护人，或后续改用用户级缓存 |

## 13. 实施顺序

1. **核心**：`runtime/config.py` 项目内查找、`bootstrap.ps1`、`scripts/sync_project.py`、`scripts/update.py`、`update.ps1`、`scripts/install.py` portable 渲染。
2. **技能**：`project-layout.md`、5 个 `SKILL.md` 的第 0 步与路径段、`runtime-contract.md`。
3. **文档与验证**：README、usage、pytest、临时业务仓库手工验收。

每步完成后跑 `pytest`，最后按第 11 节做一次端到端验收。

## 14. 后续（不在本期）

- Mac/Linux 的 `bootstrap.sh`。
- 公司内部 Python 镜像地址，替换 python.org 提示。
- sync 的 CI 校验：检测业务仓库 `data-tools/VERSION` 是否落后。
- 技能前置自动检测 `requirements.txt` 变化并提示重跑 bootstrap。
- 静默自动更新（本期只做提示 + 一键更新）。
- 多项目共享一份 `data-tools/` 的 monorepo 形态。
