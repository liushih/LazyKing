# 项目内布局与路径解析

业务仓库内置 data-tools 后的目录约定，以及 5 个技能共用的「第 0 步：环境检查」细节。

## 目录布局

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
│   └── .venv/                         # 本机生成，不提交
├── .data-tools/                       # 项目数据根
│   ├── config.yaml                    # 提交：default_project
│   ├── projects/<项目ID>/
│   │   ├── adapter.yaml               # 提交：团队共享业务规则
│   │   ├── pitfalls.md                # 提交：团队共享坑库
│   │   ├── report.yaml                # 提交（可选）
│   │   ├── git_hosts.yaml             # 提交（可选，只含 token 键名）
│   │   ├── scripts/                   # 提交：impl 步骤代码、复杂业务模块
│   │   ├── browser/                   # 提交：浏览器测试记忆
│   │   │   ├── browser.yaml           # 环境、登录、默认参数
│   │   │   ├── flows/*.yaml           # 可复跑流程
│   │   │   └── pitfalls.md            # 浏览器坑库
│   │   ├── .env.example               # 提交：键名模板
│   │   └── .env                       # 不提交：各人凭据
│   ├── templates/<项目ID>/            # 提交（可选）
│   ├── reports/                       # 不提交：报告产物
│   └── browser/                       # 不提交：profile、浏览器报告、诊断包、probe
```

`data-tools/.venv/`、`.data-tools/projects/*/.env`、`ledger.csv`、`.token.json`、
`.data-tools/projects/*/scripts/state.json`、`.data-tools/reports/`、
`.data-tools/browser/` 和 `.update-check.json` 由同步工具写入 `.gitignore`，不进仓库。

复杂业务的 impl 模块（如登录客户端、链路封装）也放 `projects/<项目ID>/scripts/`，
随业务仓库提交；不要写死 `C:\project\claudeTool`、`hexin-data-gen`、`hexin-db-tools`
等旧路径。凭据读项目 `.env`，token 缓存写 `projects/<项目ID>/.token.json`。

## `<TOOLS_DIR>` 的解析

`<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`，按顺序确定：

1. 从当前目录向上逐级查找 `data-tools/`。
2. 找不到时读环境变量 `DATA_TOOLS_DIR`。
3. 仍找不到时读 `~/.data-tools/config.yaml` 的 `tools_dir`（`setup.ps1` 会为全局用户写入）。
4. 仍找不到就问用户业务仓库根目录，不猜。

命令里保留 `<TOOLS_DIR>` 占位符，不写死本机绝对路径；换机器或 clone 到别的目录都不会失效。

## `<DATA_HOME>` 的解析

`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`，按顺序确定：

1. 先读环境变量 `DATA_TOOLS_HOME`。
2. 没有时从当前目录向上逐级查找 `.data-tools/`。
3. 仍找不到回退 `~/.data-tools`。

运行时统一由 `runtime/config.py` 的 `data_home()` 解析，优先级为
**`DATA_TOOLS_HOME` > 最近祖先 `.data-tools/` > `~/.data-tools`**。技能里的
解析顺序与它保持一致；不要自行拼绝对路径。

`<数据目录>` 即 `<DATA_HOME>`。

## Python 检查

解释器优先用项目内虚拟环境：

- Windows：`<TOOLS_DIR>/.venv/Scripts/python.exe`
- POSIX：`<TOOLS_DIR>/.venv/bin/python`

没有 venv 时依次检查 `py -3.11 --version`、`py -3 --version`、
`python --version`、`python3 --version`，要求 **Python 3.11+**。

`py -3` 可能指向旧版本，必须解析 `--version` 输出后再判断，不能只看命令是否存在。

都没有或版本过低时：

1. 提示用户到 <https://www.python.org/downloads/> 下载安装 Python 3.11+。
2. 提醒安装时勾选 **Add python.exe to PATH**。
3. 停止当前任务，不代装、不自动下载、不修改系统 PATH。

## bootstrap.ps1

有 Python 3.11+ 但没有 `.venv` 时，运行：

```powershell
powershell -ExecutionPolicy Bypass -File <TOOLS_DIR>/bootstrap.ps1
```

脚本会创建 `.venv`、升级 pip、安装 `requirements.txt`；带 `-ProjectId <ID>` 时
还会创建 `.data-tools/projects/<ID>/` 骨架。幂等：`.venv` 已存在时只补装依赖。

`-CheckOnly` 的退出码：

| 退出码 | 含义 |
|---|---|
| 0 | `.venv` 路径已存在（不保证其中的解释器可正常使用） |
| 1 | 未检测到 Python 3.11+ |
| 2 | Python 可用，但 `.venv` 不存在 |

## update.ps1

技能第 0 步用下面这条命令顺带检查版本：

```powershell
<TOOLS_DIR>/update.ps1 -CheckOnly -Quiet
```

- `-CheckOnly`：只检查，不更新；有新版本时退出码 10。
- `-Quiet`：无新版本时不输出；有新版本仍打印提示。

有新版本时，技能询问用户「发现新版本，是否现在更新？」。用户确认后运行 `update.ps1`，
完成后提醒提交 `data-tools/`、生成的技能入口和 `.gitignore`；用户拒绝则继续，
本次会话不再追问。脚本不存在、无新版本、检查失败或 `update_check` 关闭时继续。

更新检查成功按 `check_interval_hours`（默认 24 小时）缓存；失败按
`failure_cooldown_minutes`（默认 15 分钟）冷却，避免离线时每次技能启动都等网络。
在 `.data-tools/config.yaml` 的 `data_tools` 段可以设置 `update_check: false` 彻底关闭检查。

## 浏览器测试的数据边界

- 提交：`.data-tools/projects/<项目ID>/browser/browser.yaml`、`flows/*.yaml`、`pitfalls.md`，以及项目 `scripts/` 下的 impl。
- 不提交：`.data-tools/browser/`（profile、reports、artifacts、probes）。
- `browser.yaml` 只写 `${VAR}`；新增键时同步更新 `.env.example`。

## adapter-bootstrap 的额外约定

接入完成后，同时维护项目 `.env.example` 的键名，不写值。`.env.example` 提交进
仓库，`.env` 只留在本机；新增或改名凭据时先更新 `.env.example`，再让用户填 `.env`。
