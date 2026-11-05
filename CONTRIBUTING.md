# 贡献约定

本仓库是**通用工具**，服务于多个项目。进入 git 的内容必须与具体项目无关。

## 进 git 的（通用能力）

- 运行时代码：`runtime/`
- 命令行入口：`scripts/`（不含写死某个项目表名、接口路径的脚本）
- 技能规则与模板：`skills/`（用占位符表示项目信息，如 `<项目ID>`、`<业务对象>`）
- 测试：`tests/`
- 设计与计划文档：`docs/superpowers/`
- 插件与市场清单：`.claude-plugin/`、`.cursor-plugin/`、`.codex-plugin/`

## 发布新版本

版本号以 `.claude-plugin/plugin.json` 为唯一来源（同事的更新检查和插件市场都读它），`marketplace.json` 里不写 `version`。
不要手改，用脚本一次同步 Claude、Codex、Cursor 三个清单，测试 `test_version_sync.py` 会拦住不一致：

```powershell
.venv/Scripts/python.exe scripts/bump_version.py 1.5.2
```

通过插件市场安装的用户只在版本号变化时才会收到更新，所以改了行为就要升版本，再提交推送。

### 升版本是提交的一部分

这条对人和所有 AI 编码助手（Claude Code、Codex、Cursor 等）一视同仁：**升版本由提交者自己完成，不等别人提醒。**

- 改了运行行为（`runtime/`、`scripts/`、`skills/` 里的规则与模板、配置默认值、插件清单）：提交前必须升版本，和功能放在**同一个提交**里。
- 新增功能升小版本（`1.7.0` → `1.8.0`）；修复升补丁版本（`1.8.0` → `1.8.1`）；不兼容的改动升大版本。
- 只改文档、测试、设计与计划文档：不升版本。
- 步骤：`scripts/bump_version.py <新版本>` → `tests/test_version_sync.py` → `scripts/check_secrets.py` → 提交，提交信息写「……并升版本至 X.Y.Z」。
- 是否推送由使用者决定：使用者没有要求时，提交后询问，不自行推送。

判断标准：**换一个项目，这份代码还能用，不需要改。**

## 不进 git 的（项目衍生物）

以下内容属于项目衍生物，不能进入 claudeTool 仓库；其中本机私有的部分还必须在业务仓库的 `.gitignore` 里挡住：

- **业务脚本**：写死了某个项目的表名、接口路径、状态值、单号规则的脚本。不能进 claudeTool 仓库；团队模式下放业务仓库的 `.data-tools/projects/<项目ID>/scripts/` 并提交
- **运行产物**：日志（`*.err`、`*.log`）、台账（`*.csv`）、导出结果、截图
- **凭据与令牌**：`.env`、`*.token*.json*`、浏览器登录态、任何含密码的文件
- **项目配置**：适配层、坑库、项目脚本、报告模板等。个人/全局方式下它们位于 `~/.data-tools/projects/<项目ID>/`；团队方式下随业务仓库提交，都不进本仓库
- **本机私有数据**：凭据 `.env`、台账 `ledger.csv`、报告产物 `reports/`、更新检查缓存等，无论哪种方式都不提交

判断标准：**这份东西换一个项目就没用，或者含有只属于某个项目或某个人的信息。**

## 团队项目接入时的共享与本地边界

业务仓库内置 `data-tools/` 后，`.data-tools/` 下的内容要区分团队共享和本机私有。以下路径都在业务仓库的 `.data-tools/` 下。

**提交进业务仓库（团队共享）**

- `projects/<项目ID>/adapter.yaml`：业务规则
- `projects/<项目ID>/pitfalls.md`：坑库
- `projects/<项目ID>/report.yaml`、`projects/<项目ID>/git_hosts.yaml`、`projects/<项目ID>/jenkins.yaml`：报告、代码托管与发版配置；只写团队事实与 `${KEY}` 占位符，不写个人值
- `projects/<项目ID>/personal.example.yaml`：个人键清单（键名、说明、默认值来源），不写值
- `projects/<项目ID>/.env.example`：密钥键名清单，不写值
- `projects/<项目ID>/scripts/`：`impl` 步骤代码，包括 `chain.py`、`hexin_client.py` 等复杂业务模块
- `templates/<项目ID>/`：报告模板（即 `.data-tools/templates/<项目ID>/`，与 `projects/` 平级）

划分规则：身份（`USER_TAG`）、本机路径（`REPO_PATH`、`REPORT_REPOS`）、个人账号（`JENKINS_USER`、`ZENTAO_ACCOUNT`）、作者列表进个人；服务器地址、项目/产品 ID、模块映射、分支规则、流程步骤留共享；密码与令牌进 `.env`。

业务脚本不要依赖旧 `claudeTool`、`hexin-data-gen`、`hexin-db-tools`；需要的模块复制到 `projects/<项目ID>/scripts/`，凭据读项目 `.env`，token 缓存写 `projects/<项目ID>/.token.json`。

**不提交（本机私有或运行产物）**

- `projects/<项目ID>/personal.yaml`：个人值，每人一份
- `projects/<项目ID>/.env`：密钥，每人一份
- `projects/<项目ID>/ledger.csv`：运行台账
- `projects/<项目ID>/.token.json`：登录 token 缓存
- `projects/<项目ID>/scripts/state.json`：探针状态
- `scripts/__pycache__/`：Python 缓存
- `reports/`：报告产物
- `.update-check.json`、`*.log` 等缓存与日志

`scripts/sync_project.py` 会把上述忽略规则写进业务仓库 `.gitignore` 的
`# data-tools:begin` 块。共享配置里只写变量名或 token 键名，值一律放各自本机的 `.env`。

## 提交前检查

1. `git status` 确认只有通用文件
2. `python scripts/check_secrets.py` 无输出（未发现敏感信息）
3. 新增的脚本，先问自己：换项目还能用吗？不能就不要 `add`

## 历史遗留

`hexin-db-tools/`、`hexin-data-gen/`、`hexin-e2e/` 是早期的 hexincloud 专用工具，目前仍在仓库中，是待整理的历史遗留，**不作为新代码的参考**。新增的业务相关内容应放到 `~/.data-tools/projects/<项目ID>/`（个人/全局）或业务仓库的 `.data-tools/projects/<项目ID>/`（团队内置）中。
