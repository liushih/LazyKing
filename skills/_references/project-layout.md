# 项目内布局与路径解析

业务仓库本地安装 data-tools 后的目录约定，以及技能共用的「第 0 步：环境检查」细节。
**data-tools/、.data-tools/ 和生成的技能入口只在本机使用，不进入业务仓库 git。**

## 目录布局

```text
<业务仓库>/
├── data-tools/                        # 本机安装，不提交
│   ├── skills/                        # 规则源（含 _references、_TEMPLATE）
│   ├── runtime/
│   ├── scripts/
│   ├── requirements.txt
│   ├── bootstrap.ps1                  # 首次接入与环境检查
│   ├── update.ps1                     # 版本检查与一键更新
│   ├── VERSION                        # 版本 + 源 commit + 同步时间
│   └── .venv/                         # 本机生成，不提交
├── .claude/skills/                    # 生成的技能入口，不提交（仅 data-tools 技能目录）
└── .data-tools/                       # 本机数据根，不提交
    ├── config.yaml                    # default_project
    ├── projects/<项目ID>/
    │   ├── adapter.yaml               # 本机：业务规则
    │   ├── pitfalls.md                # 本机：坑库
    │   ├── report.yaml                # 本机（可选）
    │   ├── git_hosts.yaml             # 本机（可选，只含 token 键名）
    │   ├── jenkins.yaml               # 本机（可选，只含地址、账号与模块映射）
    │   ├── scripts/                   # 本机：impl 步骤代码、复杂业务模块
    │   ├── browser/                   # 本机：浏览器测试记忆
    │   │   ├── browser.yaml           # 环境、登录、默认参数
    │   │   ├── flows/*.yaml           # 可复跑流程
    │   │   ├── controls.md            # 控件操作记录，失败后累积
    │   │   └── pitfalls.md            # 浏览器坑库
    │   ├── personal.example.yaml      # 本机：个人键清单
    │   ├── personal.yaml              # 本机：本人个人值
    │   ├── .env.example               # 本机：密钥键名模板
    │   └── .env                       # 本机：各人密钥
    ├── templates/<项目ID>/            # 本机（可选）
    ├── reports/                       # 本机：报告产物
    └── browser/                       # 本机：profile、浏览器报告、诊断包、probe
```

同步工具会把 `/data-tools/`、`/.data-tools/` 和生成出来的技能目录整体写进业务仓库 `.gitignore`。已有业务仓库如果之前提交过这些路径，同步工具会提示用 `git rm -r --cached` 移出版本库；本地文件保留。

复杂业务的 impl 模块（如登录客户端、链路封装）也放 `projects/<项目ID>/scripts/`，只在本机使用；不要写死 `C:\project\LazyKing`、`hexin-data-gen`、`hexin-db-tools` 等旧路径。凭据读项目 `.env`，token 缓存写 `projects/<项目ID>/.token.json`。

团队共享的 adapter、坑库、脚本和模板通过公司内网制品库或共享目录分发，每人放到自己的 `.data-tools/`；不要用 `git add -f` 绕过忽略规则。

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
只更新本机副本；不要提醒提交任何 data-tools 变更。用户拒绝则继续，本次会话不再追问。
脚本不存在、无新版本、检查失败或 `update_check` 关闭时继续。

更新检查成功按 `check_interval_hours`（默认 24 小时）缓存；失败按
`failure_cooldown_minutes`（默认 15 分钟）冷却，避免离线时每次技能启动都等网络。
在 `.data-tools/config.yaml` 的 `data_tools` 段可以设置 `update_check: false` 彻底关闭检查。

## 个人配置

共享 yaml、`personal.yaml`、`.env` 都只在本机。团队共享 yaml 只写团队事实与 `${KEY}`；个人非敏感值写 `personal.yaml`，密钥写 `.env`。`personal.example.yaml` 与 `.env.example` 也只在本机。新增变量时按是否密钥更新对应 example；`config.py check` 会校验共享配置与 example 的覆盖关系。首次使用或提示缺个人配置时运行 `project-setup`，不要让用户修改共享 yaml。

## 浏览器测试的数据边界

- 全部在本机：`.data-tools/projects/<项目ID>/browser/browser.yaml`、`flows/*.yaml`、`controls.md`、`pitfalls.md`，以及项目 `scripts/` 下的 impl。
- 运行产物 `.data-tools/browser/`（profile、reports、artifacts、probes）也在本机，不提交。
- `browser.yaml` 只写团队地址和 `${VAR}`；新增键时按是否密钥更新 `.env.example` 或 `personal.example.yaml`。
- 团队共享走内网制品库或共享目录，不走业务仓库 git。

## adapter-bootstrap 的额外约定

接入完成后，按变量是否密钥维护 `.env.example` 或 `personal.example.yaml`；只写键名与说明，不写值。两者都只在本机。新增或改名变量时先更新对应 example，再让用户运行 `project-setup` 或填 `.env`。
