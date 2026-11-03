# Jenkins 发版能力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增第 7 个技能 `jenkins-deploy`：根据当前分支改动推断模块，经用户确认后触发对应 Jenkins 任务并回报结果。

**Architecture:** `runtime/jenkins/` 放配置、模块推断、HTTP 客户端三个单一职责文件；`scripts/jenkins.py` 是命令行入口（`setup / discover / modules / build / status`）；技能规则放 `skills/jenkins-deploy/SKILL.md`。结构、配置、凭据、同步方式全部照搬 `git-workflow`（`runtime/git_host/`、`scripts/git_host.py`）。

**Tech Stack:** Python 3.11+、`requests`（已在 `requirements.txt`）、`PyYAML`、pytest。不新增依赖。

**Spec:** `docs/superpowers/specs/2026-11-03-jenkins-deploy-design.md`

## Global Constraints

- 只支持 Python；不新增第三方依赖。
- 测试一律用假 session / 假 client，不连真实 Jenkins；解释器用 `.venv/Scripts/python.exe`。
- token 只存项目 `.env`（键名默认 `JENKINS_TOKEN`）；不得出现在命令行参数、标准输出、错误信息、日志、测试快照里。`setup` 从 **stdin** 读 token。
- 测试里的合成令牌所在行末尾加 `# noqa: secrets`（`scripts/check_secrets.py` 的跳过标记）；测试里的地址用 `http://jenkins.example.com`，不用内网 IP。
- 触发构建的 POST 请求**不自动重试**；只读请求可重试。
- 触发前必须能 `--dry-run` 回显；真正触发由技能在用户明确说「确认」或「执行」后才调用 `build`。
- 命令行入口退出码：成功 0；构建失败/中止/规则拒绝 1；用法或配置错误 2（与 `scripts/git_host.py` 的 `EXIT_OK/EXIT_FAIL/EXIT_USAGE` 一致）。
- 脚本开头与 `scripts/git_host.py` 一样：`sys.path.insert(0, 仓库根)`，`sys.stdout.reconfigure(encoding="utf-8")`。
- 技能文件命令块里不得有以 `\` 结尾的续行（`tests/test_skills.py` 会检查）。
- 每次 commit 信息以中文 conventional 风格书写，并以 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` 结尾。
- 版本号最终升到 `1.6.0`，只用 `scripts/bump_version.py`。

## Review Focus

1. 某个模块没有所选环境的任务（`jobs` 缺该环境键）：必须在**触发任何构建之前**整体报错，不能 A 已触发、B 才报错。→ Task 6。
2. 无参数的任务：`/buildWithParameters` 会 400，必须走 `/build`；有参数的任务即使模块没写 `params` 也要走 `/buildWithParameters`。→ Task 4、6。
3. Jenkins 文件夹里的任务（`folder/job`）：URL 必须拼成 `/job/folder/job/job`，`discover` 要能列出文件夹内的任务。→ Task 3。
4. `.env` 末尾无换行、或已有 `JENKINS_TOKEN` 行：`setup` 追加/替换后不能把两行粘在一起，也不能留下旧值；token 末尾的换行要去掉。→ Task 1。
5. 分支与基线相同（无改动）、基线引用不存在、改动路径里混入反斜杠：给出明确提示，不抛 traceback，不误判为命中。→ Task 2。

---

### Task 1: 配置读写（`runtime/jenkins/config.py`）

**Files:**
- Create: `runtime/jenkins/__init__.py`（空）
- Create: `runtime/jenkins/config.py`
- Test: `tests/test_jenkins_config.py`

**Interfaces:**
- Produces:
  - `class JenkinsConfigError(Exception)`
  - `@dataclass ModuleSpec`：`name: str`、`paths: list[str]`、`jobs: dict[str, str]`、`params: dict[str, str]`
  - `@dataclass JenkinsConfig`：`base_url: str`、`user: str`、`token_key: str`、`baseline: str`、`build_timeout_minutes: int`、`modules: list[ModuleSpec]`（保持 yaml 书写顺序）
  - `load_jenkins_config(project_id: str, home: Path | None = None) -> JenkinsConfig`
  - `read_token(project_id: str, token_key: str, home: Path | None = None) -> str`
  - `save_credentials(project_id: str, base_url: str, user: str, token: str, token_key: str = "JENKINS_TOKEN", home: Path | None = None) -> None`
  - 目录解析沿用 `runtime/git_host/config.py` 的 `_base(project_id, home)` 写法：`home` 给了用 `home/projects/<id>`，否则 `runtime.config.project_dir(id)`。

- [ ] **Step 1: Write the failing tests**（`home=tmp_path`，文件在 `tmp_path/projects/demo/`）
  - `test_load_reads_modules_in_yaml_order`：写入含两个模块的 `jenkins.yaml`，断言 `[m.name for m in cfg.modules] == ["order-service", "pay-service"]`，`baseline == "origin/dev"`（缺省值），`build_timeout_minutes == 30`（缺省值），`cfg.modules[0].jobs == {"dev": "b2d-order-dev"}`，`params == {"BRANCH": "{branch}"}`。
  - `test_load_missing_file_names_path`：断言 `JenkinsConfigError` 且消息含 `jenkins.yaml`。
  - `test_load_rejects_missing_required_fields`：参数化缺 `base_url` / `user` / `token_key` 各一次，断言报错消息含字段名。
  - `test_load_rejects_module_without_jobs_or_paths`：模块缺 `jobs` 抛错；`paths` 含空串抛错。
  - `test_load_allows_empty_modules`：`setup` 之后、`discover` 之前 `modules` 缺省或为空，加载得到 `modules == []`。
  - `test_read_token_missing_reports_key_only`：`.env` 无该键，断言消息含 `JENKINS_TOKEN` 且不含任何值。
  - `test_save_credentials_creates_yaml_and_env`：新建项目目录下调用，断言 yaml 的 `jenkins.base_url/user/token_key` 正确、`modules == {}`、`baseline == "origin/dev"`，`.env` 含 `JENKINS_TOKEN=<token>`；`yaml` 文本不含 token。
  - `test_save_credentials_preserves_existing_modules`：已有 `modules` 和 `baseline: origin/test`，再 `save_credentials` 后二者不变，`jenkins` 段被更新。
  - `test_save_credentials_env_edge_cases`（Review Focus 4）：`.env` 无结尾换行且有别的键 → 追加后两行分开；已有旧 `JENKINS_TOKEN=old` → 被替换且只剩一行；token 传入 `"abc\n"` → 写入 `abc`。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_config.py -q`，期望 ImportError/FAIL。

- [ ] **Step 3: Implement** 上述签名。校验失败统一抛 `JenkinsConfigError`（中文消息）。`save_credentials` 用 `yaml.safe_load` 读、`yaml.safe_dump(..., sort_keys=False, allow_unicode=True)` 写（注释不保留）；`.env` 逐行处理，替换同名键或在末尾追加，写入前确保前一行以换行结束。

- [ ] **Step 4: Run to verify pass** — 同 Step 2，期望全部 PASS。

- [ ] **Step 5: Commit** — `git add runtime/jenkins tests/test_jenkins_config.py && git commit -m "feat: 增加 Jenkins 配置读写"`

---

### Task 2: 模块推断（`runtime/jenkins/modules.py`）

**Files:**
- Create: `runtime/jenkins/modules.py`
- Test: `tests/test_jenkins_modules.py`

**Interfaces:**
- Consumes: Task 1 的 `ModuleSpec`。
- Produces:
  - `class ModulesError(Exception)`
  - `infer_modules(changed: list[str], modules: list[ModuleSpec]) -> tuple[list[ModuleSpec], list[str]]` — 返回（命中的模块，保持 yaml 顺序且去重；未映射的文件，保持输入顺序）。
  - `changed_files(repo: Path, baseline: str) -> list[str]` — 当前 HEAD 相对 `merge-base(baseline, HEAD)` 的改动文件（`git diff --name-only <base> HEAD`），不含工作区未提交改动。
  - `unpushed_commits(repo: Path, branch: str) -> int | None` — `origin/<branch>` 存在时返回 `HEAD` 比它多的提交数；不存在返回 `None`。

- [ ] **Step 1: Write the failing tests**
  - `test_longest_prefix_wins`：模块 `a` 的 paths `["svc/"]`、模块 `b` 的 paths `["svc/sub/"]`，文件 `svc/sub/x.py` 只命中 `b`，`svc/y.py` 命中 `a`。
  - `test_result_keeps_yaml_order_and_dedupes`：改动先碰 `b` 再碰 `a`，返回 `[a, b]`。
  - `test_unmapped_files_listed`：`docs/readme.md` 不属于任何模块，出现在第二个返回值。
  - `test_prefix_matches_directory_boundary`：paths `["order/"]` 不命中 `order-service/x.py`。
  - `test_backslash_paths_normalised`（Review Focus 5）：`order\\x.py` 按 `order/x.py` 匹配。
  - `test_changed_files_against_baseline`：用 `tmp_path` 里 `git init` 的真实仓库——建 `main` 一次提交，切分支再提交 `svc/a.py`，`changed_files(repo, "main") == ["svc/a.py"]`；未提交的修改不计入。
  - `test_changed_files_same_as_baseline_is_empty`：在基线分支上返回 `[]`。
  - `test_changed_files_bad_baseline_raises_friendly_error`：基线引用不存在 → `ModulesError`，消息含基线名。
  - `test_unpushed_commits`：配一个本地 bare 仓库当 `origin`——已推送时 `0`，本地再提交一次后 `1`，远端没有该分支时 `None`。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_modules.py -q`。

- [ ] **Step 3: Implement** 上述三个函数。git 调用沿用 `runtime/git_host/repo.py` 的 `subprocess.run(["git","-C",...], capture_output=True, text=True, encoding="utf-8", errors="replace")` 写法；命中判定为 `file == prefix.rstrip("/")` 或 `file.startswith(prefix.rstrip("/") + "/")`，取匹配前缀最长的模块。

- [ ] **Step 4: Run to verify pass**。

- [ ] **Step 5: Commit** — `git add runtime/jenkins/modules.py tests/test_jenkins_modules.py && git commit -m "feat: 增加 Jenkins 模块推断"`

---

### Task 3: 客户端——只读部分（`runtime/jenkins/client.py`）

**Files:**
- Create: `runtime/jenkins/client.py`
- Test: `tests/test_jenkins_client_read.py`

**Interfaces:**
- Produces:
  - `class JenkinsError(Exception)`：属性 `kind: str`（`auth` / `permission` / `notfound` / `network` / `param` / `queue` / `timeout`）、`job: str | None`、`url: str | None`。
  - `@dataclass JobParam`：`name: str`、`type: str`、`default: str | None`、`choices: list[str]`；属性 `required -> bool`（仅当 `default is None` 时为真）。
  - `@dataclass BuildStatus`：`number: int`、`building: bool`、`result: str | None`、`url: str`。
  - `class JenkinsClient`，构造 `JenkinsClient(base_url: str, user: str, token: str, session=None, timeout: float = 15.0, retries: int = 2, retry_delay: float = 0.5)`；`session` 默认 `requests.Session()`，调用形式 `session.request(method, url, auth=(user, token), headers=..., timeout=..., data=...)`，响应用 `status_code / headers / text / json()`。
  - 本任务实现：`whoami() -> str`、`list_jobs() -> list[str]`（返回 `folder/job` 形式的全名，递归文件夹）、`job_params(job: str) -> list[JobParam]`、`build_status(job: str, number: int) -> BuildStatus`、`console_tail(job: str, number: int, lines: int = 50) -> str`。
  - 内部 `job_path(job: str) -> str`：`"a/b"` → `"/job/a/job/b"`；`_request(method, path, **kw)` 统一做错误映射与脱敏。

- [ ] **Step 1: Write the failing tests**（沿用 `tests/test_git_host_gitlab.py` 的 `_Resp` / `_Sess` 假对象写法，`_Sess` 记录 calls）
  - `test_uses_basic_auth_and_trims_base_url`：`base_url="http://jenkins.example.com/"`，断言请求 URL 无双斜杠且 `kwargs["auth"] == ("u", FAKE)`。
  - `test_job_path_nests_folders`（Review Focus 3）：`job_path("a/b") == "/job/a/job/b"`，`build_status("a/b", 3)` 请求了 `/job/a/job/b/3/api/json`。
  - `test_list_jobs_recurses_into_folders`：根返回 `[{"name":"top","_class":"hudson.model.FreeStyleProject"},{"name":"dir","_class":"com.cloudbees.hudson.plugins.folder.Folder"}]`，`dir` 内返回 `[{"name":"inner",...}]`，结果为 `["dir/inner", "top"]`（排序）。
  - `test_job_params_parses_definitions`：返回含 `StringParameterDefinition`（有默认值）、`ChoiceParameterDefinition`（choices）、一个 `defaultParameterValue` 为 `None` 的定义，断言 `required` 只对最后一个为真。
  - `test_job_without_params_returns_empty_list`。
  - `test_build_status_building_and_finished`：`building=True,result=None` 与 `building=False,result="SUCCESS"` 两种。
  - `test_console_tail_keeps_last_lines`：100 行文本取最后 50 行。
  - `test_console_tail_redacts_token_and_auth_header`：文本里含 FAKE token、`Authorization: Basic dTpGQUtF...`、`base64(user:token)`，输出不含这些原文（含 `***`）。
  - `test_error_mapping`：参数化 401 → `auth`、403 → `permission`（`job` 属性与消息含任务名）、404 → `notfound`；`requests.ConnectionError` → `network`，消息不含 token。
  - `test_reads_retry_on_network_error_then_succeed`：前两次抛 `requests.ConnectionError`，第三次成功（`retry_delay=0`）；全失败时抛 `network`。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_client_read.py -q`。

- [ ] **Step 3: Implement** 上述类型与方法。查询用 Jenkins `tree=` 参数：任务列表 `jobs[name,_class]`，参数 `property[parameterDefinitions[name,type,defaultParameterValue[value],choices]]`（`type` 取 `_class` 末段并去掉 `ParameterDefinition`），状态 `number,building,result,url`。`list_jobs` 以含 `Folder` 的 `_class` 判定文件夹并继续向下取。重试只用于 GET 的网络异常。脱敏函数 `_redact(text)`：替换 token、`base64(user:token)`，并把 `(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]{8,}` 替换为 `\1 ***`；所有对外异常消息与 `console_tail` 输出都经过它。

- [ ] **Step 4: Run to verify pass**。

- [ ] **Step 5: Commit** — `git add runtime/jenkins/client.py tests/test_jenkins_client_read.py && git commit -m "feat: 增加 Jenkins 客户端只读接口"`

---

### Task 4: 客户端——触发与等待

**Files:**
- Modify: `runtime/jenkins/client.py`
- Test: `tests/test_jenkins_client_write.py`

**Interfaces:**
- Consumes: Task 3 的 `JenkinsClient`、`JenkinsError`、`BuildStatus`、`_request`。
- Produces（均为 `JenkinsClient` 的方法）：
  - `trigger(job: str, params: dict[str, str] | None) -> str` — `params is None` 走 `POST <job_path>/build`；否则（含空字典）走 `POST <job_path>/buildWithParameters`，参数放 `data`。返回响应头 `Location` 里的队列项地址。
  - `wait_for_build(queue_url: str, timeout_s: float, poll_s: float = 2.0) -> int` — 轮询 `<queue_url>api/json`，有 `executable.number` 即返回；`cancelled` 为真抛 `kind="queue"`；超时抛 `kind="timeout"`。
  - `wait_finished(job: str, number: int, timeout_s: float, poll_s: float = 5.0) -> BuildStatus` — 轮询到 `building=False`；超时抛 `kind="timeout"`，异常 `url` 为构建链接。
  - 触发请求**不重试**；构造函数新增 `sleep=time.sleep` 参数供测试注入。

- [ ] **Step 1: Write the failing tests**
  - `test_trigger_with_params_posts_build_with_parameters`：断言方法 `POST`、路径以 `/buildWithParameters` 结尾、`kwargs["data"] == {"BRANCH": "feature/x"}`，返回 `Location` 值。
  - `test_trigger_without_params_uses_build_endpoint`（Review Focus 2）：`params=None` → 路径以 `/build` 结尾；`params={}` → 以 `/buildWithParameters` 结尾。
  - `test_trigger_missing_location_raises_queue_error`：201 但无 `Location` → `kind="queue"`。
  - `test_trigger_retries_once_with_crumb_on_403_crumb_error`：第一次 403 且 `text` 含 `No valid crumb`，随后 GET `/crumbIssuer/api/json` 返回 `{"crumbRequestField":"Jenkins-Crumb","crumb":"c1"}`，第二次 POST 带请求头 `Jenkins-Crumb: c1` 成功；总共 POST 两次。
  - `test_trigger_plain_403_is_permission_and_not_retried`：403 无 crumb 字样 → `kind="permission"`，POST 仅 1 次。
  - `test_trigger_network_error_not_retried`：`requests.ConnectionError` → `kind="network"`，POST 仅 1 次。
  - `test_wait_for_build_returns_number_after_polling`：前两次 `{"executable": None}`，第三次 `{"executable":{"number":57}}`，返回 57，期间 `sleep` 被调用 2 次。
  - `test_wait_for_build_cancelled_and_timeout`：`{"cancelled": True}` → `queue`；一直无 executable 且 `timeout_s=0` → `timeout`。
  - `test_wait_finished_polls_until_not_building`：`building=True` 两次后 `False,SUCCESS`；以及超时抛 `timeout` 且 `url` 非空。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_client_write.py -q`。

- [ ] **Step 3: Implement** 三个方法。crumb 重试只在写请求且 403 响应文本含 `crumb`（不分大小写）时发生一次，成功取到后把 crumb 头加到该次重试；`_request` 增加 `retry: bool` 参数，写请求传 `False`。超时用 `time.monotonic()` 判断，`sleep` 用注入的函数。

- [ ] **Step 4: Run to verify pass**（同时跑 `tests/test_jenkins_client_read.py` 确认没回归）。

- [ ] **Step 5: Commit** — `git add runtime/jenkins/client.py tests/test_jenkins_client_write.py && git commit -m "feat: 增加 Jenkins 触发构建与等待"`

---

### Task 5: 命令行（一）——`setup / discover / modules / status`

**Files:**
- Create: `scripts/jenkins.py`
- Test: `tests/test_jenkins_cli.py`

**Interfaces:**
- Consumes: Task 1–4 的配置、模块推断、客户端。
- Produces:
  - `main(argv: list[str] | None = None, client_fn=None, stdin=None) -> int`；`client_fn(cfg: JenkinsConfig, token: str) -> JenkinsClient` 默认构造真实客户端；`stdin` 默认 `sys.stdin`（测试注入 `io.StringIO`）。
  - 所有子命令带全局 `--project`（必填）。子命令：
    - `setup --base-url URL --user U`：从 `stdin` 读 token（`strip()`），调用 `save_credentials`，再 `client.whoami()` 验证，输出 `已保存配置与 JENKINS_TOKEN；已验证：登录为 <id>`。验证失败仍保留配置，输出错误，退出 1。
    - `discover [--filter KEYWORD]`：每个任务一行 `<全名>`，其后每个参数一行 `  - NAME (type) 默认=<值或无> [可选=a,b]`；`--filter` 对任务全名做不区分大小写的子串过滤。
    - `modules [--repo PATH]`（默认 `.`）：输出分支、基线、命中模块、未映射文件（最多列 20 个，其余写“另有 N 个”）、未推送提交数（`None` 输出“远端无该分支”）；命中为空退出 1，否则 0。
    - `status --job J --number N`：输出 `[结果] <job> #<n> <url>`，进行中输出 `[BUILDING]`。
  - 错误处理统一：`JenkinsConfigError` / 缺 token → 打印 `[配置] ...` 退出 2；`JenkinsError` → 打印 `[<kind>] ...` 退出 1；`ModulesError` → `[git] ...` 退出 1。

- [ ] **Step 1: Write the failing tests**（用假 client；配置通过 `monkeypatch.setenv("DATA_TOOLS_HOME", tmp_path)` 写在 `tmp_path/projects/demo/`）
  - `test_setup_reads_token_from_stdin_and_never_prints_it`：`stdin=StringIO(FAKE + "\n")`，断言 `.env` 含 token、`capsys` 的 stdout/stderr 不含 token、输出含“登录为”。
  - `test_setup_verify_failure_keeps_config_and_exits_1`：假 client 的 `whoami` 抛 `JenkinsError("auth")`，配置文件仍存在，退出 1，输出含 `[auth]`。
  - `test_discover_lists_jobs_with_params_and_filter`：假 client 有 `a/order-dev`、`pay-dev` 两个任务，`--filter ORDER` 只输出前者及其参数行。
  - `test_modules_reports_hits_and_unmapped`：在 `tmp_path` 里建真实 git 仓库（基线分支 + 特性分支改 `order-service/x.py` 与 `docs/a.md`），断言输出含命中模块名、未映射文件 `docs/a.md`，退出 0。
  - `test_modules_exit_1_when_no_hit`：分支与基线相同 → 输出“无命中模块”，退出 1。
  - `test_status_prints_result`。
  - `test_missing_config_exits_2`：无 `jenkins.yaml` → 退出 2，输出含路径。
  - `test_missing_token_exits_2_and_names_key_only`：输出含 `JENKINS_TOKEN`，不含其他值。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_cli.py -q`。

- [ ] **Step 3: Implement** `scripts/jenkins.py` 的解析器、`main` 和上述四个子命令；开头样板与 `scripts/git_host.py` 相同。

- [ ] **Step 4: Run to verify pass**。

- [ ] **Step 5: Commit** — `git add scripts/jenkins.py tests/test_jenkins_cli.py && git commit -m "feat: 增加 Jenkins 命令行 setup/discover/modules/status"`

---

### Task 6: 命令行（二）——`build`

**Files:**
- Modify: `scripts/jenkins.py`
- Test: `tests/test_jenkins_build.py`

**Interfaces:**
- Consumes: Task 5 的 `main`、解析器和错误处理；Task 4 的 `trigger / wait_for_build / wait_finished`、Task 3 的 `job_params / console_tail`。
- Produces: 子命令 `build --env E [--module M ...] [--branch B] [--sequential] [--no-wait] [--dry-run] [--repo PATH]`。
  - 模块选择：`--module` 可多次，名字须存在于配置，否则退出 2；缺省时用 Task 5 同样的推断；仍为空 → 退出 2，输出“没有可构建的模块”。
  - 分支：`--branch` 缺省取 `git rev-parse --abbrev-ref HEAD`；`params` 里的 `{branch}` 替换为该分支。
  - **预检（先于任何触发请求，对所有选中模块逐个做）**：`jobs` 缺该环境键 → 退出 2，消息含模块名与环境名；`job_params(job)` 与模块 `params` 对比，模块写了任务不认识的参数名，或任务有 `required` 参数而模块未提供 → 退出 2，消息列出参数名。
  - 触发参数：任务有声明参数 → 传字典（可为空）；任务无参数 → 传 `None`。
  - `--dry-run`：预检通过后输出 `<模块> → <任务> 参数=<k=v,...>`，每行一个，**不**触发，退出 0。
  - 默认：按配置书写顺序依次 `trigger` 全部（某个触发失败记录错误后继续下一个），再对每个已触发的构建 `wait_for_build` → `wait_finished`（超时用 `build_timeout_minutes * 60`）。`--sequential`：触发一个、等完成一个，遇到非 SUCCESS 或错误即停，其后的标记 `未触发`。`--no-wait`：只触发，输出队列地址。
  - 结果行格式：`[SUCCESS] order-service → b2d-order-dev #57 <url>`；失败/中止/不稳定的构建后追加 `console_tail(job, number)` 的内容；触发被拒的行为 `[permission] order-service → b2d-order-dev 无权构建`。
  - 退出码：全部 SUCCESS（或 `--no-wait` 全部成功触发）0；其余 1。

- [ ] **Step 1: Write the failing tests**（假 client 记录 `calls`，按任务名返回预设结果）
  - `test_dry_run_prints_plan_and_triggers_nothing`：`calls` 里没有任何 `trigger`，输出含 `order-service → b2d-order-dev` 和 `BRANCH=feature/x`。
  - `test_preflight_missing_env_job_blocks_everything`（Review Focus 1）：两个模块，第二个缺 `test` 环境任务，`--env test` → 退出 2，`calls` 里**没有** `trigger`，消息含第二个模块名与 `test`。
  - `test_preflight_unknown_and_missing_required_params`：模块 `params` 含任务没有的 `FOO` → 退出 2 且含 `FOO`；任务有 `required` 参数 `ENV_NAME` 而模块没写 → 退出 2 且含 `ENV_NAME`。
  - `test_job_without_params_triggers_with_none`（Review Focus 2）：假 client 记录 `trigger("job", None)`；有声明参数但模块 `params` 为空时记录 `trigger("job", {})`。
  - `test_default_triggers_all_in_order_then_reports`：三个模块，第二个构建 FAILURE，输出三行结果、第二行后跟日志末尾，退出 1；三次 `trigger` 都发生（第一个失败不影响后面）。
  - `test_trigger_failure_does_not_stop_others`：第一个 `trigger` 抛 `JenkinsError("permission")`，第二个仍触发；输出含 `[permission]`，退出 1。
  - `test_sequential_stops_on_first_failure`：第二个 FAILURE，第三个模块标记 `未触发`，`calls` 中第三个没有 `trigger`。
  - `test_no_wait_prints_queue_urls`：不调用 `wait_for_build`，输出队列地址，退出 0。
  - `test_unknown_module_name_exits_2`；`test_no_modules_selected_exits_2`。
  - `test_build_output_never_contains_token`：整个输出不含 FAKE token。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_build.py -q`。

- [ ] **Step 3: Implement** `build` 子命令；预检抽成独立函数 `_preflight(client, cfg, modules, env, branch) -> list[PlannedBuild]`（`PlannedBuild`：`module: str`、`job: str`、`params: dict[str, str] | None`），`--dry-run`、默认、`--sequential` 都先调用它。

- [ ] **Step 4: Run to verify pass** — `.venv/Scripts/python.exe -m pytest tests/test_jenkins_cli.py tests/test_jenkins_build.py -q`。

- [ ] **Step 5: Commit** — `git add scripts/jenkins.py tests/test_jenkins_build.py && git commit -m "feat: 增加 Jenkins build 命令"`

---

### Task 7: 技能、模板与触发词

**Files:**
- Create: `skills/jenkins-deploy/SKILL.md`
- Create: `skills/_TEMPLATE/jenkins.example.yaml`
- Modify: `skills/_TEMPLATE/env.example`（追加 `JENKINS_TOKEN=`，注释说明由 `setup` 写入）
- Modify: `skills/_references/trigger-routing.md`
- Modify: `skills/_references/project-layout.md`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: Task 5/6 的命令行用法（`setup / discover / modules / build / status` 及其参数）。
- Produces: 技能名 `jenkins-deploy`；触发词路由新增「发版」一行。

- [ ] **Step 1: Write the failing tests**（在 `tests/test_skills.py`）
  - 把 `"jenkins-deploy"` 加进两处参数化列表（frontmatter 与章节检查、命令单行检查）。
  - `test_jenkins_skill_confirms_before_build_and_protects_token`：`SKILL.md` 含 `--dry-run`、`确认`、`stdin`、`不回显`、`403`、`discover`、`jenkins.py`。
  - `test_trigger_routing_includes_jenkins`：`trigger-routing.md` 含 `发版`、`Jenkins`、`jenkins-deploy`，且“六个 skill”已改为“七个 skill”。
  - `test_jenkins_example_parses`：`jenkins.example.yaml` 经 `yaml.safe_load` 后含 `jenkins.base_url/user/token_key`、`baseline`、`modules` 且至少一个模块含 `paths/jobs/params`。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_skills.py -q`。

- [ ] **Step 3: Write the files**
  - `SKILL.md`：frontmatter 的 `description` 写触发场景（「发版」「构建」「部署」「Jenkins」「把这个需求的模块发到 dev/test」）；章节依次为 适用场景（含不适用：提交/推送→`git-workflow`）、第 0 步环境检查（照抄 `git-workflow` 的 7 步）、前置检查（含**首次流程**：问地址 → 账号候选取 git 用户标识让用户确认，也接受用户一次给出 `账号:token` 由 AI 拆开 → 请用户在对话中给 token，建议单独生成可吊销的 API token → 经 stdin 调 `setup`，之后不复述 token → `discover` 核对并生成 `modules` 映射写入 `jenkins.yaml`，提醒提交；再确认项目 ID 与环境）、路径、执行（命令示例，一律单行，路径用 `<TOOLS_DIR>` 占位）、写操作前必须回显并等待确认（用 `--dry-run` 得到回显内容，另含推送检查：`modules` 输出的未推送提交数不为 0 或远端无该分支时先提醒）、失败处理（表格照 spec 第 9 节）。
  - `jenkins.example.yaml`：照 spec 第 5 节示例，值用 `http://jenkins.example.com`，每个键加中文注释。
  - `trigger-routing.md`：表格加 `发版 | 发版、构建、部署、Jenkins、上线构建 | deploy, build, jenkins, release | jenkins-deploy`；消歧顺序在「代码托管」之后插入“含「发版 / 构建 / 部署 / Jenkins」→ `jenkins-deploy`”；开头“六个”改“七个”。
  - `project-layout.md`：布局树里加 `jenkins.yaml  # 提交（可选，只含地址、账号与模块映射）`；开头“6 个技能”改“7 个技能”。

- [ ] **Step 4: Run to verify pass** — `.venv/Scripts/python.exe -m pytest tests/test_skills.py -q`。

- [ ] **Step 5: Commit** — `git add skills tests/test_skills.py && git commit -m "feat: 增加 jenkins-deploy 技能与触发词"`

---

### Task 8: 同步、文档与版本

**Files:**
- Modify: `scripts/sync_project.py`（`PROJECT_DATA_FILES` 加 `"jenkins.yaml"`；`ENV_EXAMPLE_TEMPLATE` 追加注释行 `# JENKINS_TOKEN=`）
- Modify: `README.md`（“六个技能”→“七个技能”，表格加 `jenkins-deploy` 一行；“能做什么”表加一行“发版我这个需求的模块”）
- Modify: `docs/usage.md`（目录与第一节“六个技能”→“七个技能”，路由表与顺序同步；新增“十四、Jenkins 发版”一节并补目录链接）
- Modify: `.claude-plugin/plugin.json`（description 加“Jenkins 发版”）；版本用 `scripts/bump_version.py`
- Test: `tests/test_sync_project.py`、`tests/test_install.py`

**Interfaces:**
- Consumes: Task 7 的技能目录（`skill_names()` 自动发现，无需改 `install.py`）。

- [ ] **Step 1: Write the failing tests**
  - `tests/test_sync_project.py::test_jenkins_yaml_is_project_data`：`"jenkins.yaml" in PROJECT_DATA_FILES`；并在已有的“保留项目数据”类用例旁新增一例：项目目录下已有 `jenkins.yaml` 时，`sync` 结果的 `preserved` 含它（照该文件现有同类用例的构造方式）。
  - `tests/test_sync_project.py::test_env_example_template_mentions_jenkins_token`：`"JENKINS_TOKEN" in ENV_EXAMPLE_TEMPLATE`。
  - `tests/test_install.py::test_skill_names_discovers_jenkins_deploy`：仿 `test_skill_names_discovers_browser_test`。

- [ ] **Step 2: Run to verify failure** — `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py tests/test_install.py -q`。

- [ ] **Step 3: Implement** 上述修改；`docs/usage.md` 新节内容：首次接入（问答流程）、`jenkins.yaml` 写法与字段说明、常用说法示例（“发版我这个需求的模块到 dev”）、多模块行为（进 Jenkins 队列 / `--sequential`）、常见问题（401、403、404、参数预检失败、触发失败不自动重试、token 在对话中提供的提示）。然后运行 `.venv/Scripts/python.exe scripts/bump_version.py 1.6.0`。

- [ ] **Step 4: Run the whole suite and the scanners**
  - `.venv/Scripts/python.exe -m pytest -q` → 全部 PASS（浏览器相关用例在无 Chrome 时会 skip，属正常）。
  - `.venv/Scripts/python.exe scripts/check_secrets.py` → `未发现敏感信息`。
  - `.venv/Scripts/python.exe scripts/jenkins.py --project demo modules` 在无配置时应输出 `[配置] 未找到 jenkins.yaml` 并退出 2（手动冒烟）。

- [ ] **Step 5: Commit** — `git add scripts/sync_project.py README.md docs/usage.md .claude-plugin .codex-plugin .cursor-plugin tests && git commit -m "feat: Jenkins 发版接入同步、文档并升版本至 1.6.0"`

---

## Self-Review 记录

- **Spec 覆盖**：第 5 节配置 → Task 1；6.3 模块推断 → Task 2；6.1 客户端 → Task 3、4；第 7 节命令 → Task 5、6；第 8 节技能流程、第 9 节错误处理 → Task 7（规则）+ Task 3–6（行为）；第 10 节安全 → Global Constraints + Task 1/3/5/6 的测试；第 11 节测试 → 各任务；第 12 节同步/文档/版本 → Task 7、8。
- **与 spec 的两处细化（均不改变行为意图）**：① `discover` 增加可选 `--filter`（任务很多时避免一次拉全量参数）；② `modules` 增加 `--repo`（默认当前目录）和未推送提交数输出，供技能做推送检查；“必填参数”定义为 Jenkins 返回的参数默认值为 `null` 者。
- **类型一致性**：`ModuleSpec / JenkinsConfig`（Task 1）→ Task 2、5、6 同名使用；`JenkinsError.kind` 取值在 Task 3 定义，Task 4–6 沿用；`trigger(job, params|None)` 在 Task 4 定义、Task 6 按同一语义调用。
