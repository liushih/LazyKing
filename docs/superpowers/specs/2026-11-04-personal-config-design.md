# 团队个人配置分层设计

**日期**：2026-11-04
**状态**：待审阅
**关联**：`runtime/config.py`、`runtime/git_host/config.py`、`runtime/jenkins/config.py`、`runtime/report_config.py`、`runtime/adapter.py`、`runtime/browser/config.py`、`scripts/sync_project.py`

## 1. 背景与目标

工具包整包同步进业务仓库后，团队共享配置（Git 托管地址、Jenkins 模块映射、禅道产品 ID、造数与浏览器流程）随仓库提交；但 `user_tag`、本地仓库路径、Jenkins 账号、报告作者这类值因人而异，目前和团队事实混在同一个 yaml 里。结果是：同事要么改动被跟踪的共享文件，要么被迫使用提交者的个人值。

目标：

- 每个同事首次使用时，由 AI 问清楚自己的值，生成个人配置；不需要改共享 yaml，`git status` 不出现个人改动。
- 共享流程（`adapter.yaml`、`browser/flows/*.yaml`、Jenkins `modules`）改完后，其他人 pull 下来直接可用；只有新增变量或本人缺值时才需要补配置。
- 密钥仍然只进 `.env`，不经过对话、不进日志、不进仓库。
- 原有个人/全局模式（`~/.data-tools`）行为不变。

## 2. 现状

- 业务仓库 `C:/project/hexincloud` 的 `.data-tools/` 整体是 untracked，尚未提交过任何共享配置。
- 本地 `git_hosts.yaml` 含 `user_tag: lsh`、`repo_path: C:/project/hexincloud`；`jenkins.yaml` 含 `user: liushihao`；`report.yaml` 含本机仓库路径和作者列表。
- `.env` 已被 `.gitignore` 忽略，其余配置一旦 `git add .` 就会进仓库。
- 因此本期不需要为已提交的存量做自动迁移；只需在首次提交前建立正确的分层，并让检查命令能拦住共享文件里的个人值。

## 3. 决策

| 决策 | 选择 |
| --- | --- |
| 个人非敏感值存哪 | 项目内 `.data-tools/projects/<项目ID>/personal.yaml`，gitignore |
| 生成入口 | 新增 `project-setup` 技能负责问答，底层 `scripts/config.py` 负责校验与写入 |
| 共享/个人划分 | 按「是否因人而异」逐键划分 |
| 实现方式 | 共享 yaml 用 `${KEY}` 占位符，加载时把 `personal.yaml` 与 `.env` 合并后复用现有 `substitute` |

## 4. 非目标

- 不实现交互式 TUI 或图形配置界面。
- 不自动改写已提交的共享文件；存量由 `check` 报告后人工处理。
- 不改变造数、浏览器测试、报告采集的业务逻辑，只改配置来源。
- 不引入密钥托管服务；密钥仍由各人写入本机 `.env`。

## 5. 配置模型

### 5.1 文件布局

每个项目一份：

```text
.data-tools/projects/<项目ID>/
├── git_hosts.yaml          # 提交：团队事实 + ${个人变量}
├── jenkins.yaml            # 提交：团队事实 + ${个人变量}
├── report.yaml             # 提交：团队事实 + ${个人变量}
├── adapter.yaml            # 提交：造数流程 + ${变量}
├── browser/browser.yaml    # 提交：测试流程 + ${变量}
├── browser/flows/*.yaml    # 提交：测试流程，运行期变量不在此声明
├── personal.example.yaml   # 提交：个人键清单，含说明与默认值来源
├── personal.yaml           # 不提交：本人生成的个人值
├── .env.example            # 提交：密钥键清单
└── .env                    # 不提交：本人密钥
```

`personal.yaml` 与 `personal.example.yaml` 加入 `sync_project.py` 的 `PROJECT_DATA_FILES`，同步时绝不覆盖。`.gitignore` 的 `data-tools` 块新增 `.data-tools/projects/*/personal.yaml`。

### 5.2 逐键划分

- **个人非敏感**：身份、本机路径、个人账号、个人作者列表。示例：`USER_TAG`、`REPO_PATH`、`REPORT_REPOS`、`JENKINS_USER`、`ZENTAO_ACCOUNT`、`GIT_AUTHORS`、`ZENTAO_AUTHORS`。
- **密钥**：密码、令牌、私钥的值。放 `.env`。示例：`GITLAB_TOKEN_HEXINCLOUD`、`JENKINS_TOKEN`、`ZENTAO_PASSWORD`、数据库密码、浏览器登录密码。
- **团队事实**：服务器地址、项目/产品 ID、模块到任务映射、分支规则、流程步骤、选择器、等待信号、报告模板。留在共享 yaml 的字面值里。

判断标准：换一个人或换一台机器是否必须不同。必须不同 → 个人；所有人相同 → 团队；不能公开 → 密钥。

### 5.3 共享文件示例

```yaml
# git_hosts.yaml
user_tag: ${USER_TAG}
repo_path: ${REPO_PATH}
host:
  kind: gitlab
  base_url: http://git.hexincorp.cn:36359
  project_path: hexincloud/hexincloud
  token_key: GITLAB_TOKEN_HEXINCLOUD
branches:
  dev: dev
  test: test
  prod: prod
```

```yaml
# jenkins.yaml
jenkins:
  base_url: http://47.119.130.25:8080
  user: ${JENKINS_USER}
  token_key: JENKINS_TOKEN
baseline: origin/dev
modules:
  ui:
    paths: [Hexin_ui/]
    jobs:
      dev: ui-ERP-dev
      test: ui-ERP-test2
    params: {}
```

```yaml
# report.yaml
git:
  repos: ${REPORT_REPOS}
  authors: ${GIT_AUTHORS}
zentao:
  api: v2
  # 团队共用的地址直接写字面值；如果不同网络环境需要不同地址，
  # 改成 ${ZENTAO_URL} 并在 personal.example.yaml 或 .env.example 中声明。
  base_url: http://zentao.example.com
  account: ${ZENTAO_ACCOUNT}
  password: ${ZENTAO_PASSWORD}
  product_id: 31
  project_ids: [73, 125]
  authors: ${ZENTAO_AUTHORS}
```

### 5.4 `personal.example.yaml`

这是团队对「每个人需要提供什么」的契约，提交进仓库。格式：

```yaml
version: 1
keys:
  USER_TAG:
    description: Git 分支与提交使用的个人标识
    type: string
    default_from: git_user_name
  REPO_PATH:
    description: 本机业务仓库根目录
    type: string
    default_from: repo_root
  REPORT_REPOS:
    description: 报告要统计的仓库路径，可多个
    type: list
    default_from: repo_root
  JENKINS_USER:
    description: Jenkins 登录账号
    type: string
    default_from: user_tag
  GIT_AUTHORS:
    description: Git 提交里可能出现的作者名或账号
    type: list
    default_from: git_user_name
  ZENTAO_ACCOUNT:
    description: 禅道登录账号
    type: string
    default_from: none
  ZENTAO_AUTHORS:
    description: 禅道任务/Bug 里可能出现的完成人
    type: list
    default_from: git_user_name
```

`type` 取值 `string` 或 `list`。`default_from` 取值：

| 值 | 含义 |
| --- | --- |
| `git_user_name` | `git config user.name` |
| `repo_root` | `<TOOLS_DIR>` 的上一级，即业务仓库根目录 |
| `user_tag` | 已配置的 `USER_TAG` |
| `none` | 没有默认值，必须询问 |

`personal.yaml` 是扁平键值：

```yaml
USER_TAG: lsh
REPO_PATH: C:/project/hexincloud
REPORT_REPOS:
  - C:/project/hexincloud
JENKINS_USER: liushihao
GIT_AUTHORS:
  - liushihao
  - 刘师豪
ZENTAO_ACCOUNT: liushihao
ZENTAO_AUTHORS:
  - 刘师豪
```

`.env.example` 继续只列密钥键名，不写值。每个 `${KEY}` 必须且只能出现在 `personal.example.yaml` 或 `.env.example` 之一；两边都出现或都不出现，`config check` 报错。

### 5.5 加载顺序

新增 `runtime/config.py::load_values(project_dir: Path) -> dict[str, Any]`：

1. 读 `personal.yaml`，缺失视为空映射；
2. 读 `.env`，同名键覆盖 `personal.yaml`；
3. 返回合并后的映射。

`personal.yaml` 存在但不是合法 YAML 或顶层不是映射时，抛 `ConfigError` 并带上文件路径，不静默忽略。

浏览器测试额外保留现有行为：`lookup = {**os.environ, **load_values(base)}`，即 `.env` 优先级最高，其次是 `personal.yaml`，最后是进程环境变量。其他加载器只使用 `load_values`。

`substitute` 扩展：当整个值恰好是 `${KEY}`，且解析结果是列表或字典时，原样返回该对象；否则按现有字符串插值处理。这样 `authors: ${GIT_AUTHORS}` 可以直接对应 YAML 列表。缺失变量仍抛 `ConfigError("未定义变量 KEY")`。

所有加载器改为从 `load_values` 取值：

| 文件 | 改动 |
| --- | --- |
| `runtime/adapter.py` | `config.load_env(base / ".env")` → `config.load_values(base)` |
| `runtime/report_config.py` | 同上，替换第 50 行 |
| `runtime/git_host/config.py` | 读取后先 `substitute(raw, load_values(base))` |
| `runtime/jenkins/config.py` | 读取后先 `substitute(raw, load_values(base))` |
| `runtime/browser/config.py` | `dotenv` → `load_values`，保留 `os.environ` 叠加 |
| `scripts/browser.py` | 凡是构造变量映射处统一走 `load_values` |

兼容策略：

- 共享文件仍是字面值：不改也能跑，现有个人/全局模式不受影响。
- 有占位符但没有 `personal.yaml`：加载时报「缺少个人配置，先运行 project-setup」。
- 占位符键未在 example 中声明：`config check` 报错，阻止运行时才炸。

### 5.6 占位符扫描规则

`config check` 只扫描会引用个人值的文件与字段，避免把运行期变量误判为个人配置：

| 能力 | 扫描范围 | 说明 |
| --- | --- | --- |
| git | `git_hosts.yaml` 全文 | `user_tag`、`repo_path` |
| jenkins | `jenkins.yaml` 全文 | `jenkins.user` |
| report | `report.yaml` 全文 | 仓库列表、账号、作者 |
| adapter | `adapter.yaml` 全文 | `${ctx.xxx}` 含点号，不匹配变量正则，自动忽略 |
| browser | `browser/browser.yaml` 的 `envs`、`defaults.profile`、`login.url`、`login.username`、`login.password` | 跳过 `login.steps`；`${username}`、`${password}`、`${BASE_URL}` 是步骤内建变量 |

`browser/flows/*.yaml` 不参与个人配置扫描。流程里的 `${order_no}` 等是运行期输入，由 `--var` 或流程 `vars` 声明提供。

占位符正则为 `\$\{([A-Za-z_][A-Za-z0-9_]*)\}`，与 `runtime/config.py` 现有实现一致。

### 5.7 漂移检查

`config check` 除缺失值外，报告以下漂移：

0. **example 缺失**：`personal.example.yaml` 不存在时，所有未在 `.env.example` 中声明的占位符都报未声明，并提示运行 `config.py example --write` 生成草稿。
1. **未声明变量**：共享配置里的 `${KEY}` 不在任何一个 example 中。错误。
2. **重复声明**：同一个键同时出现在 `personal.example.yaml` 与 `.env.example`。错误。
3. **共享文件里的个人值**：
   - 已知个人路径仍是字面值，如 `git_hosts.yaml` 的 `user_tag`、`repo_path`，`jenkins.yaml` 的 `jenkins.user`，`report.yaml` 的 `git.repos`、`git.authors`、`zentao.account`、`zentao.authors`；
   - 共享 yaml 的值形如 `C:/...`、`C:\...` 或以 `/` 开头的绝对路径。警告。

警告不阻断运行，但 `project-setup` 和维护人应优先处理。

## 6. 底层命令 `scripts/config.py`

逻辑放在 `runtime/personal.py`，`scripts/config.py` 只做参数解析与输出，便于单元测试。

### 6.1 命令

```text
config.py --project <ID> check [--capability git|jenkins|report|adapter|browser] [--json]
config.py --project <ID> set KEY=值 [KEY=值 ...] [--allow-unknown]
config.py --project <ID> set-secret KEY
config.py --project <ID> example [--write]
```

### 6.2 `check`

- 不带 `--capability`：检查所有能力，输出分组报告。缺失值只报告、不阻断（退出码 0），避免没用 Jenkins 的人被挡；未声明变量、重复声明等漂移属于配置错误，退出码 2。
- 带 `--capability`：只检查该能力；缺失或漂移退出码 2，否则 0。供技能在真正使用某能力前调用。
- 共享配置不存在：该能力标记 `absent`，不算失败；由维护人或对应技能决定是否创建。
- YAML 非法：退出码 3，原样报告文件和错误。
- `--json` 输出结构：

```json
{
  "project": "hexincloud",
  "capabilities": {
    "git": {
      "status": "missing",
      "missing": [
        {
          "key": "USER_TAG",
          "target": "personal",
          "description": "Git 分支与提交使用的个人标识",
          "default_from": "git_user_name"
        }
      ],
      "drift": [
        {
          "file": "git_hosts.yaml",
          "kind": "literal_personal_value",
          "key": "user_tag",
          "message": "共享文件里仍是个人值，建议改成 ${USER_TAG}"
        }
      ]
    }
  }
}
```

`status` 取值：`ok`、`missing`、`absent`、`invalid`。`missing` 项按 `target` 分为 `personal` 与 `secret`。输出不包含任何值。

### 6.3 `set`

- 只写 `personal.yaml`，自动创建文件与目录。
- 拒绝写密钥键，提示改用 `set-secret`。
- 拒绝写未在 `personal.example.yaml` 声明的键，除非 `--allow-unknown`，防止拼写错误。
- 列表类型从 `personal.example.yaml` 的 `type` 读取；`--allow-unknown` 的键按字符串处理。
- 写入用临时文件加原子替换，键按字母序输出。
- 文件权限：POSIX 下 `0o600`；Windows 不额外处理。

### 6.4 `set-secret`

- 只写 `.env`，拒绝非密钥键；键必须已在 `.env.example` 中声明，否则拒绝，防止把拼写错误写进本机文件。
- stdin 是终端时用 `getpass` 读取；否则读入第一行。空值拒绝。
- 复用现有 `.env` 写入逻辑（按 `KEY=` 覆盖或追加），写后不打印值。
- POSIX 下 `.env` 权限设为 `0o600`。

### 6.5 `example`

- 扫描所有共享配置，得到 `${KEY}` 集合。
- 已在 `.env.example` 中的键归为密钥，其余归为个人。
- 打印建议的 `personal.example.yaml` 草稿；未知键的 `description` 留空，由维护人补。
- `--write` 只在 `personal.example.yaml` 不存在时写入草稿；已存在时只打印新增/删除的键，不覆盖。
- 不自动修改 `.env.example`，只打印需要补的密钥键。

## 7. `project-setup` 技能

新增 `skills/project-setup/SKILL.md`，触发词包括「初始化个人配置」「新同事接入」「配置我的账号」「配一下环境」「个人配置」。

流程：

1. 执行统一的第 0 步环境检查，定位 `<TOOLS_DIR>`、`<DATA_HOME>` 与项目 ID。
2. 运行 `config.py check --json`。
3. 询问需要哪些能力：造数、查库、Git、Jenkins、报告、浏览器测试。只配置选中的能力。
4. 对每个缺失的非敏感键，按 `description` 和 `default_from` 给出默认值并请用户确认。默认值来源见 5.4。
5. 用 `config.py set` 写入 `personal.yaml`。一次可写多个键。
6. 对缺失的密钥键，不在对话中索要值；打印一条让用户在自己的终端运行的命令：

   ```text
   python <TOOLS_DIR>/scripts/config.py --project <ID> set-secret JENKINS_TOKEN
   ```

   用户运行后，重新 `check` 只验证键是否存在，不读取值。
7. 重新 `config.py check --capability <能力>`，直到选中能力全部为 `ok` 或用户明确跳过。
8. 可选只读验证：`jenkins.py modules`、`browser.py doctor`、`git_host.py verify-flow`。默认不做，询问用户后再跑；失败只报告，不自动修。
9. 汇总写入的文件、仍缺的键、后续命令。明确说明 `personal.yaml` 与 `.env` 已被 gitignore，共享 yaml 未被修改。

失败处理：

| 情况 | 动作 |
| --- | --- |
| 共享配置缺失（如没有 `jenkins.yaml`） | 说明这是团队维护人任务，不在 setup 中现场创建；需要时走对应技能的首次接入流程 |
| 共享配置含未声明变量 | 报文件与键名，停下，请维护人补 example；不猜 |
| 用户不知道某个值 | 保留缺失，说明该能力暂不可用；不填占位值 |
| 用户拒绝提供密钥 | 说明对应能力不可用，继续配置其他能力 |
| `check` 仍报漂移 | 列出文件与建议，交给维护人处理 |

## 8. 各技能接入

所有能力技能的前置检查增加同一段：

```markdown
运行 `config.py check --capability <能力>`。有缺失时使用 `project-setup` 补齐，
不现场猜个人值，不修改共享 yaml。密钥只提示用户在终端运行 `set-secret`。
```

| 技能 | capability | 额外改动 |
| --- | --- | --- |
| `git-workflow` | `git` | 删除「询问 user_tag 后写共享文件」；`set-user-tag` 保留为写 `USER_TAG` 的薄命令，发现共享文件仍是字面值时提示替换 |
| `jenkins-deploy` | `jenkins` | 共享 `jenkins.yaml` 缺失 = 维护人首次接入；个人账号/token 缺失 = `project-setup`。token 改为终端输入 |
| `report-writer` | `report` | 共享 `report.yaml` 缺失 = 维护人任务；个人账号、作者、仓库列表缺失 = `project-setup` |
| `adapter-bootstrap` | `adapter` | 新增 `${变量}` 时同步更新 `personal.example.yaml` 或 `.env.example`；接入完成后跑 `check` |
| `data-gen-core` | `adapter` | 使用 `adapter.yaml` 前检查个人配置 |
| `db-access` | `adapter` | 数据库凭据缺失时走 setup |
| `browser-test` | `browser` | 流程文件保持共享；`browser.yaml` 新增变量时更新 example |

`project-setup` 自身也注册为独立技能，由 `scripts/install.py` 自动发现并渲染到各工具入口。

### 8.1 现有写配置命令的行为调整

- `git_host.py set-user-tag`：改为调用 `config set USER_TAG=<值>`，只写 `personal.yaml`。如果共享 `git_hosts.yaml` 的 `user_tag` 仍是字面值，命令成功但输出警告，提示维护人改成 `${USER_TAG}`。项目未在 `personal.example.yaml` 声明 `USER_TAG` 时拒绝写入，提示先补 example 或运行 setup。
- `jenkins.py setup`：token 写入 `.env`；`JENKINS_USER` 写入 `personal.yaml`；只有共享 `jenkins.yaml` 不存在时才创建它并写入 `base_url`、`token_key`、空的 `modules`。文件已存在时绝不覆盖 `base_url` 或 `modules`，发现 `jenkins.user` 仍是字面值就输出警告。
- `scripts/config.py` 是命令入口，内部逻辑放在 `runtime/personal.py`，避免与 `runtime/config.py` 混淆。脚本不导入同名模块，所有运行时逻辑通过 `runtime.*` 导入。

## 9. 同步工具改动

`scripts/sync_project.py`：

- `PROJECT_DATA_FILES` 增加 `personal.yaml`、`personal.example.yaml`。
- `GITIGNORE_BLOCK` 增加 `.data-tools/projects/*/personal.yaml`。
- 不生成 `personal.yaml`，不写个人值。
- `personal.example.yaml` 缺失时不在同步阶段自动创建；由 `config example --write` 或维护人创建。
- 生成的项目 README 增加三行：先 bootstrap、再 project-setup、个人文件不要提交。

## 10. 安全

- `personal.yaml` 只放非敏感值；密钥只在 `.env`。
- `config check` 与 `--json` 不输出值，只输出键名与状态。
- `set-secret` 从 stdin/终端读取，值不进入命令行参数、对话、日志。
- `config example` 只读键名，不读 `.env` 的值。
- `scripts/check_secrets.py` 仍是提交前检查；新增文档提醒共享 yaml 不得出现绝对路径和个人账号。

## 11. 迁移与 hexincloud 落地

当前 hexincloud 的 `.data-tools/` 尚未提交，因此不实现自动迁移命令。落地顺序：

1. 在 claudeTool 完成实现、测试、升版本并同步。
2. 在 `C:/project/hexincloud/.data-tools/projects/hexincloud/`：
   - `git_hosts.yaml`：`user_tag` → `${USER_TAG}`，`repo_path` → `${REPO_PATH}`；
   - `jenkins.yaml`：`jenkins.user` → `${JENKINS_USER}`；
   - `report.yaml`：`git.repos` → `${REPORT_REPOS}`，`git.authors` → `${GIT_AUTHORS}`，`zentao.authors` → `${ZENTAO_AUTHORS}`（没有则新增）；`zentao.base_url` 团队共用则改成字面值，否则保留占位并在 example 声明；
   - `adapter.yaml`、`browser/browser.yaml`：团队共享的地址改成字面值；个人账号改成 `${...}`；密码与令牌留在 `.env`。例如 `WEB_USERNAME` 进 `personal.yaml`，`WEB_PASSWORD` 留在 `.env`。
3. 生成 `personal.example.yaml`，对齐 `.env.example`。
4. 运行 `project-setup`，用当前本机值生成 `personal.yaml` 与 `.env`。
5. 跑 `config check`，全部为 `ok`。
6. `git status` 确认只出现共享 yaml 与 example；`personal.yaml`、`.env` 不出现。
7. 是否提交业务仓库由使用者决定。

其他已经提交过个人值的项目：`check` 报告 5.7 的漂移，维护人手工替换占位符后，各人再运行 setup。本期不提供自动改写。

## 12. 测试

新增 `tests/test_personal_config.py`：

- `load_values` 合并 `personal.yaml` 与 `.env`，`.env` 覆盖同名键。
- `substitute` 支持整节点列表替换，同时保留字符串插值。
- `scan_placeholders` 对 git/jenkins/report/adapter/browser 的扫描范围正确；忽略 `${ctx.xxx}` 与浏览器登录步骤内建变量。
- `check` 报告缺失、未声明、重复声明、字面个人值、绝对路径。
- `set` 拒绝密钥键与未知键；列表按逗号拆分；原子写入。
- `set-secret` 拒绝非密钥键；值不回显。
- `example --write` 不覆盖已有文件。

更新现有测试：

- `tests/test_git_host_config.py`、`tests/test_jenkins_config.py`、`tests/test_report_config.py`、`tests/test_browser_config.py`：覆盖从 `personal.yaml` 取值与缺失报错。
- `tests/test_sync_project.py`：忽略规则包含 `personal.yaml`；`personal.yaml` 与 `personal.example.yaml` 不被覆盖；重复同步幂等。
- `tests/test_install.py` 或 `tests/test_skills.py`：`project-setup` 被发现并渲染；各能力技能包含配置检查语句。

验收：

- `C:/project/hexincloud` 按第 11 节落地后，`config check` 无缺失、无漂移。
- 删除 `personal.yaml` 后，`config check --capability git` 报 `USER_TAG`、`REPO_PATH` 缺失，加载器给出 setup 提示。
- 共享 `adapter.yaml` 新增 `${NEW_VAR}` 但未更新 example 时，`check` 报未声明变量。
- 全量测试：`.venv/Scripts/python.exe -m pytest tests -q`。

## 13. 版本与文档

- 运行行为变化，升小版本：`1.8.0 → 1.9.0`，使用 `scripts/bump_version.py`。
- 更新 `CONTRIBUTING.md` 的团队共享边界，加入 `personal.yaml`、`personal.example.yaml` 与逐键划分规则。
- 更新 `docs/usage.md`：同事接入流程改为 bootstrap → project-setup → 使用。
- 更新 `skills/_references/project-layout.md`、`runtime-contract.md`。
- 更新 `skills/_TEMPLATE/project-readme.md`。
- 提交信息示例：`feat: 个人配置分层与 project-setup 并升版本至 1.9.0`。
- 提交后按仓库约定询问是否推送。

## 14. 风险与取舍

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 两处个人文件（`personal.yaml` 与 `.env`）让用户困惑 | 把值写错文件 | `check` 按 `target` 分组提示；`set` 与 `set-secret` 拒绝错位写入；文档用一句话说明「非敏感进 personal，密码令牌进 .env」 |
| `personal.example.yaml` 与共享配置漂移 | 同事缺值或填了无用键 | `check` 强制每个 `${KEY}` 恰好声明一次；`example` 打印差异 |
| 浏览器登录步骤内建变量被误扫 | setup 要求填 `username`/`password` | 扫描跳过 `login.steps`，只扫 `login.username`、`login.password` |
| 适配层运行期变量被误扫 | setup 要求填 `ctx.*` | 变量正则不含点号，天然忽略 |
| 列表值含逗号 | `set` 拆分错误 | 提示直接编辑 `personal.yaml`；文档写明 |
| 同事不需要某能力却被缺值阻断 | 用不了其他能力 | `check` 按能力检查；setup 先让用户选择能力 |
| 共享文件里的个人值未清理 | 同事误用提交者的账号/路径 | `check` 警告；首次提交前按第 11 节清理 |
| Windows 路径反斜杠 | YAML 转义错误 | `set` 用 `yaml.safe_dump` 写入，自动加引号 |
| 进程环境变量与个人配置冲突 | 行为不一致 | 统一优先级：`.env` > `personal.yaml` > `os.environ`（仅浏览器保留环境变量叠加） |

## 15. 实施顺序

1. `runtime/config.py` 的 `load_values`、列表替换、占位符扫描；`runtime/personal.py` 的检查与写入逻辑；单元测试。
2. 五个加载器切换到 `load_values`；更新现有配置测试。
3. `scripts/config.py` 命令层与测试。
4. `project-setup` 技能与各技能前置检查；技能测试。
5. `sync_project.py` 忽略规则与保留名单；同步测试。
6. 文档、升版本、全量测试、提交。
7. 在 hexincloud 落地并验收（是否提交业务仓库由使用者决定）。
