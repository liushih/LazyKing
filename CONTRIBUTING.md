# 贡献约定

本仓库是**通用工具**，服务于多个项目。进入 claudeTool 仓库的内容必须与具体项目无关；集成进业务仓库时，所有 data-tools 相关内容一律只留本机，不进入业务仓库 git。

## 一、仓库边界

| 内容 | 进 claudeTool git | 进业务仓库 git | 说明 |
| --- | --- | --- | --- |
| `runtime/`、`scripts/` 通用代码 | 是 | — | 换项目还能直接用 |
| `skills/` 规则与模板 | 是 | — | 用 `<项目ID>`、`<业务对象>` 等占位符 |
| `tests/`、`docs/superpowers/` | 是 | — | 测试、设计与计划 |
| 插件与市场清单 | 是 | — | `.claude-plugin/`、`.cursor-plugin/`、`.codex-plugin/` |
| `data-tools/` 本机副本 | 否 | 否 | 由同步工具安装，写进业务仓库 `.gitignore` |
| `.data-tools/` 适配层、坑库、脚本、模板 | 否 | 否 | 团队共享走内网制品库或共享目录 |
| 生成的技能入口 | 否 | 否 | `.claude/skills/<技能>/`、`.cursor/rules/<技能>.mdc`、`.dsh/skills/<技能>/` |
| 凭据、台账、报告、日志、浏览器数据 | 否 | 否 | 任何 git 都不进 |

判断标准：

- **claudeTool 仓库**：换一个项目，这份代码还能用，不需要改。
- **业务仓库**：data-tools 相关内容只在本机，不进入业务系统的版本库与审计范围。

## 二、业务仓库集成的硬规则

团队模式把工具同步到业务仓库的本机副本，但 `data-tools/`、`.data-tools/` 和生成的技能入口一律由同步工具写进业务仓库 `.gitignore`，不得提交。

- `data-tools/`：工具源码、运行时、命令行入口、技能规则。
- `.data-tools/`：适配层、坑库、项目脚本、模板、个人配置、台账、报告、浏览器数据。
- 生成的技能入口：`.claude/skills/<data-tools 技能>/`、`.cursor/rules/<data-tools 技能>.mdc`、`.dsh/skills/<data-tools 技能>/`。
- `AGENTS.md` 中的 `data-tools` 块：同步工具会主动移除；团队模式不再生成 codex 入口。

已有业务仓库如果之前提交过上述路径，执行 `git rm -r --cached -- <路径>` 后提交删除；本地文件保留。不得用 `git add -f` 绕过。团队共享的适配层、坑库和脚本通过公司内网制品库或共享目录分发，具体渠道由团队 IT 决定。

这样做的原因是供应链与合规：业务仓库只保留业务代码，第三方工具、AI 规则和本机凭据不进入业务系统的版本库与审计范围。

## 三、团队文件怎么放

业务仓库本地安装 `data-tools/` 后，`data-tools/` 和 `.data-tools/` 下的所有内容都只在本机。同步工具会把整个目录写进 `.gitignore` 的 `# data-tools:begin` 块。

**团队内部分发（不进 git）**

以下文件由团队维护，通过公司内网制品库或共享目录分发，每人放到自己的 `.data-tools/`：

- `projects/<项目ID>/adapter.yaml`：业务规则。
- `projects/<项目ID>/pitfalls.md`：坑库。
- `projects/<项目ID>/report.yaml`、`git_hosts.yaml`、`jenkins.yaml`：报告、代码托管与发版配置；只写团队事实与 `${KEY}` 占位符，不写个人值。
- `projects/<项目ID>/personal.example.yaml`：个人键清单（键名、说明、默认值来源），不写值。
- `projects/<项目ID>/.env.example`：密钥键名清单，不写值。
- `projects/<项目ID>/scripts/`：`impl` 步骤代码，包括 `chain.py`、`hexin_client.py` 等复杂业务模块。
- `templates/<项目ID>/`：报告模板（即 `.data-tools/templates/<项目ID>/`，与 `projects/` 平级）。

划分规则：身份（`USER_TAG`）、本机路径（`REPO_PATH`、`REPORT_REPOS`）、个人账号（`JENKINS_USER`、`ZENTAO_ACCOUNT`）、作者列表进个人；服务器地址、项目/产品 ID、模块映射、分支规则、流程步骤留团队；密码与令牌进 `.env`。

业务脚本不要依赖旧 `claudeTool`、`hexin-data-gen`、`hexin-db-tools`；需要的模块复制到 `projects/<项目ID>/scripts/`，凭据读项目 `.env`，token 缓存写 `projects/<项目ID>/.token.json`。

**一律不进业务仓库 git**

- `projects/<项目ID>/personal.yaml`：个人值，每人一份。
- `projects/<项目ID>/.env`：密钥，每人一份。
- `projects/<项目ID>/ledger.csv`：运行台账。
- `projects/<项目ID>/.token.json`：登录 token 缓存。
- `projects/<项目ID>/scripts/state.json`：探针状态。
- `scripts/__pycache__/`：Python 缓存。
- `reports/`：报告产物。
- `.update-check.json`、`*.log` 等缓存与日志。
- 上面「团队内部分发」里的全部文件，也不要提交。

`scripts/sync_project.py` 会把 `/data-tools/`、`/.data-tools/` 和生成的技能入口整体写进业务仓库 `.gitignore`，已跟踪的路径会提示用 `git rm -r --cached` 移出版本库。共享配置里只写变量名或 token 键名，值一律放各自本机的 `.env`。

## 四、版本与发布

版本号以 `.claude-plugin/plugin.json` 为唯一来源（同事的更新检查和插件市场都读它），`marketplace.json` 里不写 `version`。不要手改，用脚本一次同步 Claude、Codex、Cursor 三个清单，测试 `test_version_sync.py` 会拦住不一致：

```powershell
.venv/Scripts/python.exe scripts/bump_version.py <新版本>
```

通过插件市场安装的用户只在版本号变化时才会收到更新，所以改了行为就要升版本，再提交（推送前询问使用者）。

### 升版本是提交的一部分

这条对人和所有 AI 编码助手（Claude Code、Codex、Cursor 等）一视同仁：**升版本由提交者自己完成，不等别人提醒。**

- 改了运行行为（`runtime/`、`scripts/`、`skills/` 里的规则与模板、配置默认值、插件清单）：提交前必须升版本，和功能放在**同一个提交**里。
- 新增功能升小版本（`1.7.0` → `1.8.0`）；修复升补丁版本（`1.8.0` → `1.8.1`）；不兼容的改动升大版本。
- 只改文档、测试、设计与计划文档：不升版本。
- 步骤：`scripts/bump_version.py <新版本>` → `tests/test_version_sync.py` → `scripts/check_secrets.py` → 提交，提交信息写「……并升版本至 X.Y.Z」。
- 是否推送由使用者决定：使用者没有要求时，提交后询问，不自行推送。

## 五、提交前检查

1. `git status` 确认只有通用文件。
2. `.venv/Scripts/python.exe scripts/check_secrets.py` 无输出（未发现敏感信息）。
3. 新增的脚本，先问自己：换项目还能用吗？不能就不要 `add`。

## 六、历史遗留

`hexin-db-tools/`、`hexin-data-gen/`、`hexin-e2e/` 是早期的 hexincloud 专用工具，目前仍在仓库中，是待整理的历史遗留，**不作为新代码的参考**。新增的业务相关内容应放到 `~/.data-tools/projects/<项目ID>/`（个人/全局）或业务仓库的 `.data-tools/projects/<项目ID>/`（团队本机安装，不提交）中。
