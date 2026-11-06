# Jenkins 发版能力设计

**日期**：2026-11-03
**状态**：待审阅
**关联**：`skills/jenkins-deploy/`、`runtime/jenkins/`、`scripts/jenkins.py`、`scripts/sync_project.py`、`skills/_references/trigger-routing.md`

## 1. 背景与目标

LazyKing 已有 6 项能力。开发完一个需求后，发版仍要人去 Jenkins 页面逐个点模块。目标是增加第 7 项能力：用户说「发版我这个需求的模块」，AI 根据当前需求的改动推断要构建的模块，触发对应的 Jenkins 任务并汇报结果。

成功标准：

- 首次使用时，AI 询问 Jenkins 地址、账号、token，之后沿用，不再询问。
- 同事在业务仓库里说「发版」，AI 能算出改动涉及的模块，回显后经确认触发构建。
- 构建结果（成功/失败、链接、失败日志末尾）直接回报，不用再开页面看。
- 没有权限时明确提示，不绕过。
- 配置随业务仓库共享，token 只存本机、不进仓库、不进日志。

## 2. 决策摘要

| 决策 | 选择 | 理由 |
|---|---|---|
| 落点 | 独立第 7 个技能 `jenkins-deploy` | 与 `git-workflow` 同构；凭据与规则不混；`skills/` 自动发现 |
| 实现 | Python 运行时 `runtime/jenkins/` + `scripts/jenkins.py` | 可单元测试；符合「只支持 Python」 |
| 模块来源 | 当前分支改动推断 + 回显确认；推不出来由用户直接说模块名 | 用户选定 |
| 任务映射 | 首次连接后 `discover` 列出任务与参数，与用户一起生成 `jenkins.yaml` | 用户不确定 Jenkins 任务结构，先看后定 |
| 认证 | 标准 Basic：账号 + API token；账号默认取 git 用户标识，用户确认 | 用户选「按标准走」 |
| 凭据收集 | token 在对话中提供，AI 经 stdin 写入本机 `.env`，不回显 | 用户选定；仅对 Jenkins 例外，不改 `git-workflow` 的令牌规则 |
| 环境 | 由用户指定，工具不设白名单；无权限（403）时提示用户 | 用户选定，权限交给 Jenkins |
| 多模块 | 默认按 yaml 顺序依次触发，全部进 Jenkins 队列，由 Jenkins 决定串行/并行；可选 `--sequential` 等前一个成功再触发下一个 | 与用户在页面上逐个点击的习惯一致 |
| 写操作 | 触发前必须回显并等待用户确认 | 构建影响他人，沿用 `git-workflow` 约定 |

## 3. 范围

**做**

- `runtime/jenkins/`：客户端、配置、模块映射。
- `scripts/jenkins.py`：`setup`、`discover`、`modules`、`build`、`status`。
- 技能 `skills/jenkins-deploy/SKILL.md`，触发词路由更新。
- 模板 `jenkins.example.yaml`，`env.example` 增加 `JENKINS_TOKEN`。
- 同步、安装、文档、测试、版本升至 1.6.0。

**不做**

- Jenkins 任务的创建、修改、删除。
- 模块间依赖编排（顺序以 yaml 书写顺序为准）。
- prod 额外白名单或二次确认机制（权限交给 Jenkins，确认沿用通用回显）。
- bearer / 纯 token 认证。
- 构建产物下载、发布后的验证联动。

## 4. 目录与文件

```text
LazyKing/
├── runtime/jenkins/
│   ├── __init__.py
│   ├── client.py        # Jenkins HTTP 客户端
│   ├── config.py        # 读 jenkins.yaml / token
│   └── modules.py       # 改动文件 → 模块
├── scripts/jenkins.py   # 命令行入口
├── skills/jenkins-deploy/SKILL.md
├── skills/_TEMPLATE/jenkins.example.yaml
└── tests/test_jenkins_*.py

业务仓库/.data-tools/projects/<项目ID>/
├── jenkins.yaml         # 提交：地址、账号、模块映射（无密钥）
└── .env                 # 不提交：JENKINS_TOKEN
```

`sync_project.py` 的 `PROJECT_DATA_FILES` 加入 `jenkins.yaml`，同步时不覆盖人维护的映射。

## 5. 配置：`jenkins.yaml`

```yaml
jenkins:
  base_url: http://jenkins.example.com
  user: liushihao
  token_key: JENKINS_TOKEN       # 值在本机 .env
baseline: origin/dev             # 推断模块时的对比基线
build_timeout_minutes: 30
modules:                         # 书写顺序即触发顺序
  order-service:
    paths: [order-service/]      # 改动命中这些路径 → 该模块
    jobs: {dev: b2d-order-dev, test: b2d-order-test}   # 环境 → 任务名
    params: {BRANCH: "{branch}"} # 构建参数；{branch} 为当前分支
```

- `jobs` 的环境键由用户在接入时定，不预设 dev/test/prod 集合。
- 校验：`base_url`、`user`、`token_key` 必填；每个模块至少有一个 `jobs`；路径前缀不得为空。
- 实际任务名、参数名在接入时由 `discover` 的输出核对，避免手写错。

## 6. 运行时组件

### 6.1 `client.py`

`JenkinsClient(base_url, user, token)`，Basic 认证。

| 方法 | 说明 |
|---|---|
| `list_jobs()` | `/api/json?tree=jobs[name,url]`，含文件夹内任务（递归一层以上按需） |
| `job_params(job)` | 任务的参数定义：名称、类型、默认值、可选项 |
| `trigger(job, params)` | `buildWithParameters`，返回队列项地址；无参数任务用 `build` |
| `wait_for_build(queue_url, timeout)` | 轮询队列项，拿到构建号；被取消则报错 |
| `build_status(job, number)` | 是否在构建、结果（SUCCESS/FAILURE/ABORTED/UNSTABLE）、链接 |
| `console_tail(job, number, lines=50)` | 控制台末尾，输出前脱敏 |

- 写请求遇到 `No valid crumb` 的 403：取 crumb 后重试**一次**；此外**触发请求不自动重试**（避免重复构建）。
- 只读请求（列表、状态、轮询）可重试。
- 错误统一为 `JenkinsError`，带类别：`auth`（401）、`permission`（403，含任务名）、`notfound`（404）、`network`、`param`。

### 6.2 `config.py`

- `load_jenkins_config(project_id)` 读 `jenkins.yaml`，缺文件报路径。
- `read_token(...)` 从项目 `.env` 读 `token_key`；缺失只报键名。
- `save_credentials(project_id, base_url, user, token)`：写 `jenkins.yaml` 的 `jenkins` 段和 `.env` 的键；保留文件里其余内容。

### 6.3 `modules.py`

- `infer_modules(changed_files, modules)`：对每个文件取最长匹配的 `paths` 前缀，返回 `(命中模块列表（保持 yaml 顺序）, 未映射文件列表)`。
- 改动文件来自 `git diff --name-only <merge-base(baseline, HEAD)> HEAD`；工作区未提交的改动单独提示，不计入。

## 7. 命令行 `scripts/jenkins.py`

所有命令带 `--project <项目ID>`。

| 命令 | 作用 | 写操作 |
|---|---|---|
| `setup --base-url URL --user U` | 写 `jenkins.yaml`；**token 从 stdin 读**，写入 `.env`；成功后做一次连通性检查 | 本地写 |
| `discover` | 列出任务及各自参数定义，供生成映射 | 否 |
| `modules` | 输出命中的模块与未映射文件 | 否 |
| `build --env E [--module M ...] [--branch B] [--sequential] [--no-wait] [--dry-run]` | 触发构建 | 是 |
| `status --job J --number N` | 查某次构建 | 否 |

`build` 细节：

1. 未指定 `--module` 时按 `modules` 推断。
2. 触发前用 `job_params` 预检：缺少必填参数或传了未知参数，直接报错，不发请求。
3. `--dry-run` 只输出将要触发的任务和参数，不发请求（技能回显确认时使用）。
4. 默认依次触发所有任务（全部进 Jenkins 队列），再同时轮询；全部结束后汇总。
5. `--sequential`：等前一个成功再触发下一个，失败即停。
6. `--no-wait`：只触发，输出队列/构建链接。
7. 退出码：全部成功 0；有构建失败或被中止 1；用法错误 2。

token 绝不出现在命令行参数、标准输出和日志中。

## 8. 技能流程 `skills/jenkins-deploy`

1. **第 0 步**：环境检查（与其他技能一致，沿用 `project-layout.md`）。
2. **前置检查**：
   - 缺 `jenkins.yaml` 或缺 token → **首次流程**：
     1. 询问地址；账号用 git 用户标识作候选让用户确认（也接受用户一次给出 `账号:token`）。
     2. 请用户在对话中提供 token（建议单独生成、权限够用、可随时吊销的 API token）。
     3. 经 stdin 调 `setup`，后续回复不复述 token。
     4. 运行 `discover`，与用户核对任务和参数，生成 `modules` 映射并写入 `jenkins.yaml`、提醒提交。
   - 确认项目 ID、环境（用户指定，没说就问）。
3. **推断模块**：`modules`；有未映射文件时列出并询问，不猜。
4. **推送检查**：本地 HEAD 与 `origin/<分支>` 不一致时提醒，Jenkins 构建的是远端代码。
5. **回显并等待确认**：Jenkins 地址、分支、环境、模块 → 任务、参数（用 `--dry-run` 得到）。只有用户明确说「确认」或「执行」才运行 `build`。
6. **汇报**：每个任务的结果与链接；失败附控制台末尾 50 行。

## 9. 错误处理

| 情况 | 动作 |
|---|---|
| 401 | 报「账号或 token 无效」，引导重新提供，不重试 |
| 403（任务级） | 报「当前账号无权构建 `<任务名>`」，提示联系管理员，不重试、不换方式 |
| 404 | 报任务不存在，建议重跑 `discover` 更新映射 |
| 参数预检失败 | 报缺少/多余的参数名，不发请求 |
| 网络不通/超时 | 报错；**不自动重试触发**；轮询阶段可重试 |
| 排队被取消 / ABORTED / UNSTABLE | 原样报状态和链接 |
| 等待超过 `build_timeout_minutes` | 报超时与构建链接，构建本身不取消 |
| 缺 `jenkins.yaml` | 进入首次流程 |
| 缺 token | 进入首次流程（只报键名） |

## 10. 安全

- token 只存项目 `.env`；`.env` 已在同步写入的 `.gitignore` 范围内。
- `setup` 经 stdin 接收 token，不进 argv / 进程列表 / shell 历史。
- 控制台与错误输出做令牌样式脱敏（复用现有脱敏工具的做法）后再回显。
- token 因在对话中提供，会留在对话记录里：技能提示用户使用单独生成、可吊销的 API token。
- `check_secrets.py` 不应误报；测试里的令牌使用合成值并标注。

## 11. 测试

用 mock HTTP，不连真实 Jenkins。

- `client`：Basic 头；crumb 重试仅一次；参数化触发；队列 → 构建号；轮询状态；401/403/404 分类；触发不重试；只读重试。
- `config`：读 yaml、字段校验；缺 token 只报键名；`save_credentials` 保留其余内容。
- `modules`：最长前缀；未映射文件；无改动；保持 yaml 顺序。
- CLI：`--dry-run` 内容；参数预检；`setup` 经 stdin 且输出不含 token；`--sequential` 失败即停；退出码。
- 脱敏：控制台含令牌样式字符串时被替换。
- `test_skills.py` 纳入 `jenkins-deploy`；`test_sync_project.py` 覆盖 `jenkins.yaml` 不被覆盖。

## 12. 同步、文档与版本

- `sync_project.py`：`PROJECT_DATA_FILES` 加 `jenkins.yaml`；新技能、运行时、脚本由白名单自动带入。
- `_TEMPLATE/jenkins.example.yaml`、`env.example` 增加 `JENKINS_TOKEN`。
- `trigger-routing.md`：新增「发版」行，触发词：发版、构建、部署、Jenkins、上线构建；消歧顺序在「代码托管」之后插入。
- README：「六个技能」改为「七个技能」并加一行；`docs/usage.md` 增加「Jenkins 发版」一节（首次接入、`jenkins.yaml` 写法、常见问题）。
- 版本用 `scripts/bump_version.py` 升至 1.6.0。

## 13. 风险与开放点

- Jenkins 任务有文件夹层级或参数命名各异，靠首次 `discover` 核对；映射写错时参数预检会拦下。
- 模块路径映射依赖业务仓库目录结构，首次需要与用户确认。
- 若 Jenkins 前置了网关、不接受 Basic 认证，需要后续单独支持（本期不做）。
