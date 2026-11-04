# 个人配置分层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让业务仓库的每个成员用自己的 `personal.yaml` 和 `.env` 提供个人值与密钥，共享 yaml 只保留团队事实和 `${KEY}` 占位符。

**Architecture:** 共享配置通过 `runtime/config.py::load_values` 合并 `personal.yaml`（非敏感个人值）与 `.env`（密钥）后做变量替换。新增 `runtime/personal.py` 负责扫描、检查、写入；新增 `scripts/config.py` 提供 `check/set/set-secret/example`；新增 `project-setup` 技能负责首次问答。

**Tech Stack:** Python 3.11+、PyYAML、pytest、argparse。

**Spec:** [2026-11-04-personal-config-design.md](../specs/2026-11-04-personal-config-design.md)

## Global Constraints

- Python 3.11+；Windows 与 POSIX 都要工作，路径用 `pathlib`。
- `runtime/`、`scripts/`、`skills/` 不得写死 `hexincloud`、`C:/project/...` 等项目信息。
- 分享的 yaml 只允许团队事实与 `${KEY}`；个人非敏感值进 `personal.yaml`，密钥进 `.env`。
- `personal.yaml`、`.env` 必须被同步工具写入 `.gitignore`；`personal.example.yaml`、`.env.example` 提交。
- 技能文件里的命令必须是单行，不能有反斜杠续行（`tests/test_skills.py` 会检查）。
- 每个技能必须有 frontmatter 和 `## 适用场景`、`## 前置检查`、`## 执行`、`## 失败处理`，并包含标准 `## 第 0 步：环境检查`。
- 改了运行行为就升版本；本计划最终升到 `1.9.0`，与功能同一个提交。
- **提交策略**：按 `AGENTS.md`，运行行为改动必须与升版本在同一个提交。Task 1-9 只做测试与检查点，**不执行 `git commit`**；所有实现、文档和版本在 Task 10 一次性提交为 `1.9.0`。不要在各任务里单独提交。
- 全量测试：`.venv/Scripts/python.exe -m pytest tests -q`。
- 提交前运行 `scripts/check_secrets.py`，无输出。
- 提交后询问是否推送，不自行推送。

## Review Focus

1. **新克隆缺个人配置**：共享 yaml 有 `${USER_TAG}` 但没有 `personal.yaml` 时，五个加载器必须报「缺少个人配置，先运行 project-setup」，不能抛原始 traceback 或静默用空值。Task 2、5、6、7 覆盖。
2. **列表值替换**：`authors: ${GIT_AUTHORS}` 必须得到 YAML 列表；列表被嵌入更大字符串时（`x-${GIT_AUTHORS}`）必须报清晰的 `ConfigError`，不能出现 `TypeError`。Task 1 覆盖。
3. **旧字面值兼容**：共享文件里仍是 `user_tag: lsh`、`jenkins.user: liushihao` 的旧项目，`set-user-tag` 与 `jenkins.py setup` 必须保持旧行为，不能被新的 example 要求挡住。Task 2、5、6 覆盖。
4. **浏览器内建变量**：`browser.yaml` 的 `login.steps` 里 `${username}`、`${password}`、`${BASE_URL}` 不能出现在个人键清单里；`browser/flows/*.yaml` 的运行期变量同样不能。Task 2、7 覆盖。
5. **密钥不泄露**：`check`、`check --json`、`set-secret` 的输出不能包含任何密钥值；密钥不能被写进 `personal.yaml`。Task 2、3、4 覆盖。

---

## File Map

| 文件 | 责任 |
| --- | --- |
| `runtime/config.py` | 读取 `personal.yaml` 与 `.env`，变量替换；`write_env_key` |
| `runtime/personal.py` | 能力到配置文件的映射、占位符扫描、漂移检查、个人值写入、example 生成 |
| `scripts/config.py` | `check/set/set-secret/example` 命令入口 |
| `runtime/git_host/config.py` | Git 托管配置替换与 `user_tag` 写回 |
| `runtime/jenkins/config.py` | Jenkins 配置替换与凭据写回 |
| `runtime/report_config.py` | 报告配置替换 |
| `runtime/adapter.py` | 适配层配置替换 |
| `runtime/browser/config.py` | 浏览器配置替换 |
| `scripts/browser.py` | doctor 的变量齐全检查 |
| `scripts/git_host.py` | `set-user-tag` 的占位符/字面值分支 |
| `scripts/jenkins.py` | `setup` 的占位符/字面值分支 |
| `skills/project-setup/SKILL.md` | 首次个人配置问答 |
| `skills/*/SKILL.md` | 各能力接入配置检查 |
| `scripts/sync_project.py` | 忽略规则与保留名单 |
| `skills/_TEMPLATE/project-readme.md` | 同事接入说明 |

---

### Task 1: `load_values` 与列表替换

**Files:**
- Modify: `runtime/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_values(project_dir: Path) -> dict[str, Any]`
- Produces: `substitute(value: Any, env: dict[str, Any]) -> Any`

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 追加：

```python
def test_load_values_merges_personal_and_env(tmp_path):
    (tmp_path / "personal.yaml").write_text(
        "USER_TAG: lsh\nGIT_AUTHORS: [liushihao, 刘师豪]\nFROM_ENV: personal\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("FROM_ENV=dotenv\nTOKEN=secret\n", encoding="utf-8")
    assert config.load_values(tmp_path) == {
        "USER_TAG": "lsh",
        "GIT_AUTHORS": ["liushihao", "刘师豪"],
        "FROM_ENV": "dotenv",
        "TOKEN": "secret",
    }


def test_load_values_without_personal_reads_env_only(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    assert config.load_values(tmp_path) == {"TOKEN": "x"}


def test_load_values_rejects_non_mapping(tmp_path):
    (tmp_path / "personal.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="personal.yaml"):
        config.load_values(tmp_path)


def test_load_values_rejects_bad_yaml(tmp_path):
    (tmp_path / "personal.yaml").write_text("a: [\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="personal.yaml"):
        config.load_values(tmp_path)


def test_substitute_whole_value_returns_list():
    assert config.substitute("${AUTHORS}", {"AUTHORS": ["a", "b"]}) == ["a", "b"]


def test_substitute_rejects_list_inside_string():
    with pytest.raises(config.ConfigError, match="AUTHORS"):
        config.substitute("x-${AUTHORS}", {"AUTHORS": ["a"]})


def test_write_env_key_replaces_and_preserves_others(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER=1\nJENKINS_TOKEN=old\n", encoding="utf-8")
    config.write_env_key(path, "JENKINS_TOKEN", "new")
    assert path.read_text(encoding="utf-8").splitlines() == ["OTHER=1", "JENKINS_TOKEN=new"]
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL，`AttributeError: module 'runtime.config' has no attribute 'load_values'`。

- [ ] **Step 3: 实现**

在 `runtime/config.py` 增加：

```python
_FULL_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

def load_values(project_dir: Path) -> dict[str, Any]:
    """读取个人值：personal.yaml 提供非敏感值，.env 覆盖同名键。"""

def write_env_key(path: Path, key: str, value: str) -> None:
    """按 KEY= 覆盖或追加，保留其他行；POSIX 下把文件权限设为 0600。"""
```

`substitute` 改为接受 `dict[str, Any]`：整值匹配 `${KEY}` 时原样返回 `env[key]`；否则正则替换，遇到非字符串值抛 `ConfigError(f"变量 {key} 不是字符串，不能嵌入字符串")`。`load_values` 在 `personal.yaml` 不是合法 YAML 或顶层不是映射时抛 `ConfigError`，消息包含文件路径。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 1 的测试命令与结果；按 Global Constraints，留到 Task 10 统一提交。

---

### Task 2: 占位符扫描与检查

**Files:**
- Create: `runtime/personal.py`
- Test: `tests/test_personal_config.py`

**Interfaces:**
- Consumes: `runtime.config.load_env`、`runtime.config.ConfigError`
- Produces: `PersonalConfigError(ConfigError)`
- Produces:

```python
@dataclass(frozen=True)
class KeySpec:
    description: str = ""
    type: str = "string"          # string | list
    default_from: str = "none"    # git_user_name | repo_root | user_tag | none

@dataclass(frozen=True)
class MissingKey:
    key: str
    target: str                   # personal | secret
    description: str = ""
    default_from: str = "none"

@dataclass(frozen=True)
class Drift:
    file: str
    kind: str
    key: str | None = None
    message: str = ""

@dataclass(frozen=True)
class CapabilityReport:
    status: str                   # ok | missing | absent | invalid
    missing: tuple[MissingKey, ...] = ()
    drift: tuple[Drift, ...] = ()

@dataclass(frozen=True)
class CheckReport:
    project: str
    capabilities: dict[str, CapabilityReport]
    drift: tuple[Drift, ...] = ()
```

- Produces: `check(project_id: str, capability: str | None = None, home: Path | None = None) -> CheckReport`
- Produces: `report_json(report: CheckReport) -> dict[str, Any]`

**扫描约定：**

```python
CAPABILITIES = ("git", "jenkins", "report", "adapter", "browser")
SHARED_FILES = {
    "git": ("git_hosts.yaml",),
    "jenkins": ("jenkins.yaml",),
    "report": ("report.yaml",),
    "adapter": ("adapter.yaml",),
    "browser": ("browser/browser.yaml",),
}
TOKEN_KEY_PATHS = {
    "git": (("host", "token_key"),),
    "jenkins": (("jenkins", "token_key"),),
}
KNOWN_PERSONAL = {
    "git_hosts.yaml": (("user_tag",), ("repo_path",)),
    "jenkins.yaml": (("jenkins", "user"),),
    "report.yaml": (("git", "repos"), ("git", "authors"), ("zentao", "account"), ("zentao", "authors")),
}
BROWSER_SCAN_PATHS = (
    ("envs",), ("defaults", "profile"), ("login", "url"),
    ("login", "username"), ("login", "password"),
)
BROWSER_RUNTIME_VARS = {"BASE_URL", "username", "password"}
PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/)")
```

- [ ] **Step 1: 写失败测试**

创建 `tests/test_personal_config.py`，包含以下用例：

```python
def test_check_reports_missing_personal_key(tmp_path):
    # git_hosts.yaml 只含 user_tag: ${USER_TAG}
    # personal.example.yaml 声明 USER_TAG；没有 personal.yaml
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "missing"
    assert [m.key for m in report.capabilities["git"].missing] == ["USER_TAG"]
    assert report.capabilities["git"].missing[0].target == "personal"


def test_check_reports_missing_secret_token_key(tmp_path):
    # jenkins.yaml 含 jenkins.user: u（字面值）、jenkins.token_key: JENKINS_TOKEN
    # .env.example 声明 JENKINS_TOKEN；没有 .env
    report = personal.check("demo", "jenkins", home=tmp_path)
    assert [m.key for m in report.capabilities["jenkins"].missing] == ["JENKINS_TOKEN"]
    assert report.capabilities["jenkins"].missing[0].target == "secret"


def test_check_reports_undeclared_placeholder(tmp_path):
    # adapter.yaml 使用 ${NEW_VAR}，两个 example 都没声明
    report = personal.check("demo", "adapter", home=tmp_path)
    assert any(d.kind == "undeclared_variable" and d.key == "NEW_VAR" for d in report.capabilities["adapter"].drift)


def test_check_reports_duplicate_declaration(tmp_path):
    # USER_TAG 同时出现在 personal.example.yaml 与 .env.example
    report = personal.check("demo", "git", home=tmp_path)
    assert any(d.kind == "duplicate_declaration" for d in report.capabilities["git"].drift)


def test_check_warns_literal_personal_value(tmp_path):
    # git_hosts.yaml 仍是 user_tag: lsh；personal.example.yaml 存在
    report = personal.check("demo", "git", home=tmp_path)
    assert any(d.kind == "literal_personal_value" and d.key == "user_tag" for d in report.capabilities["git"].drift)


def test_check_warns_absolute_path(tmp_path):
    # report.yaml 的 zentao 段出现 C:/project/demo
    report = personal.check("demo", "report", home=tmp_path)
    assert any(d.kind == "absolute_path" for d in report.capabilities["report"].drift)


def test_check_skips_browser_builtins_and_flow_vars(tmp_path):
    # browser.yaml login.steps 使用 ${username}/${password}，flows/smoke.yaml 使用 ${order_no}
    report = personal.check("demo", "browser", home=tmp_path)
    keys = {m.key for m in report.capabilities["browser"].missing}
    assert "username" not in keys and "password" not in keys and "order_no" not in keys


def test_check_ignores_dotted_runtime_placeholders(tmp_path):
    # adapter.yaml 步骤体使用 ${ctx.external_no}
    report = personal.check("demo", "adapter", home=tmp_path)
    assert all(m.key != "ctx" for m in report.capabilities["adapter"].missing)


def test_check_absent_capability(tmp_path):
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "absent"


def test_check_invalid_yaml_reports_invalid(tmp_path):
    # jenkins.yaml 写入 "jenkins: [unclosed"
    report = personal.check("demo", "jenkins", home=tmp_path)
    assert report.capabilities["jenkins"].status == "invalid"


def test_check_invalid_personal_yaml_reports_invalid(tmp_path):
    # git_hosts.yaml 使用 ${USER_TAG}，personal.yaml 写坏
    report = personal.check("demo", "git", home=tmp_path)
    assert report.capabilities["git"].status == "invalid"


def test_report_json_has_no_values(tmp_path):
    # personal.yaml 里放 PERSONAL_VALUE_LEAK
    payload = json.dumps(personal.report_json(personal.check("demo", "git", home=tmp_path)), ensure_ascii=False)
    assert "PERSONAL_VALUE_LEAK" not in payload
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_personal_config.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'runtime.personal'`。

- [ ] **Step 3: 实现 `runtime/personal.py`**

实现读取与扫描：

- `_base(project_id, home)` 返回 `(Path(home) / "projects" / project_id)` 或 `config.project_dir(project_id)`。
- `_read_yaml(path, label) -> dict`：缺失返回 `None`；YAML 非法或顶层不是映射抛 `PersonalConfigError`。
- `_placeholders(value) -> set[str]`：递归收集字符串里的 `${KEY}`，含点号的不匹配。
- `_get(data, path: tuple[str, ...]) -> Any`：按路径取值，缺失返回 `None`。
- `_scan(capability, base) -> tuple[str, set[str], list[Drift]]`：返回 `absent/missing/ok/invalid`、占位符集合、漂移。`browser` 只扫 `BROWSER_SCAN_PATHS`，并减去 `BROWSER_RUNTIME_VARS`；其他能力全文扫描。
- 对 `git`、`jenkins` 读取 `TOKEN_KEY_PATHS` 的值，加入必需的密钥集合；值不在 `.env.example` 时产生 `undeclared_variable` 漂移。
- 字面个人值与绝对路径：`KNOWN_PERSONAL` 中的字符串或列表元素只要非空且不含 `${`，产生 `literal_personal_value`；任意共享 yaml 字符串匹配 `ABSOLUTE_PATH` 产生 `absolute_path`。

`check` 规则：

- `personal.example.yaml` 缺失时，所有非密钥占位符报 `undeclared_variable`，并加顶层漂移 `missing_example`。
- 一个键同时出现在 `personal.example.yaml` 与 `.env.example`：`duplicate_declaration`。
- 键只在 personal example：`personal.yaml` 没有对应值时 `missing`，`target="personal"`。
- 键只在 `.env.example`：`.env` 没有对应值时 `missing`，`target="secret"`。
- 无缺失时 `status="ok"`；文件不存在 `status="absent"`；YAML 非法 `status="invalid"`。读取 `personal.yaml` 失败时，所有选中能力都标记 `status="invalid"`，并加漂移 `invalid_personal_yaml`。
- 顶层 `drift` 记录 `unused_declaration`（example 声明了但所有共享配置都没用到）和 `missing_example`。
- 字面个人值与绝对路径按 `(file, kind, key)` 去重。
- `report_json` 只输出键名、状态、描述、默认来源和漂移信息，绝不包含值。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_personal_config.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 2 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 3: 个人值与密钥写入

**Files:**
- Modify: `runtime/personal.py`
- Test: `tests/test_personal_config.py`

**Interfaces:**
- Consumes: Task 2 的 `KeySpec`、`_base`、`_read_yaml`、`_scan`
- Produces: `set_value(project_id, values: dict[str, str], *, allow_unknown=False, home=None) -> list[str]`
- Produces: `set_secret(project_id, key: str, value: str, *, home=None) -> None`
- Produces: `write_known_value(project_id, key: str, value: Any, *, home=None) -> None`
- Produces: `build_example(project_id, home=None) -> dict[str, KeySpec]`
- Produces: `write_example(project_id, *, force=False, home=None) -> Path | None`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_set_value_writes_personal_yaml(tmp_path):
    # personal.example.yaml 声明 USER_TAG、REPO_PATH
    personal.set_value("demo", {"USER_TAG": "lsh", "REPO_PATH": "C:/repo"}, home=tmp_path)
    data = yaml.safe_load((tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8"))
    assert data == {"REPO_PATH": "C:/repo", "USER_TAG": "lsh"}


def test_set_value_splits_list(tmp_path):
    # GIT_AUTHORS 的 type 是 list
    personal.set_value("demo", {"GIT_AUTHORS": "liushihao, 刘师豪"}, home=tmp_path)
    data = yaml.safe_load((tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8"))
    assert data["GIT_AUTHORS"] == ["liushihao", "刘师豪"]


def test_set_value_rejects_secret_key(tmp_path):
    with pytest.raises(personal.PersonalConfigError, match="set-secret"):
        personal.set_value("demo", {"JENKINS_TOKEN": "x"}, home=tmp_path)


def test_set_value_rejects_unknown_key(tmp_path):
    with pytest.raises(personal.PersonalConfigError, match="未在 personal.example.yaml"):
        personal.set_value("demo", {"TYPO": "x"}, home=tmp_path)


def test_set_secret_writes_env_only(tmp_path):
    personal.set_secret("demo", "JENKINS_TOKEN", "secret-value", home=tmp_path)
    base = tmp_path / "projects" / "demo"
    assert "JENKINS_TOKEN=secret-value" in (base / ".env").read_text(encoding="utf-8")
    assert not (base / "personal.yaml").exists()


def test_set_secret_rejects_personal_key(tmp_path):
    with pytest.raises(personal.PersonalConfigError, match=".env.example"):
        personal.set_secret("demo", "USER_TAG", "x", home=tmp_path)


def test_set_secret_rejects_empty(tmp_path):
    with pytest.raises(personal.PersonalConfigError, match="不能为空"):
        personal.set_secret("demo", "JENKINS_TOKEN", "  ", home=tmp_path)


def test_write_example_does_not_overwrite(tmp_path):
    path = tmp_path / "projects" / "demo" / "personal.example.yaml"
    path.write_text("version: 1\nkeys: {USER_TAG: {description: old}}\n", encoding="utf-8")
    assert personal.write_example("demo", home=tmp_path) is None
    assert "description: old" in path.read_text(encoding="utf-8")


def test_write_example_generates_known_defaults(tmp_path):
    # git_hosts.yaml 使用 ${USER_TAG} 与 ${REPO_PATH}
    personal.write_example("demo", home=tmp_path)
    data = yaml.safe_load((tmp_path / "projects" / "demo" / "personal.example.yaml").read_text(encoding="utf-8"))
    assert data["keys"]["USER_TAG"]["default_from"] == "git_user_name"
    assert data["keys"]["REPO_PATH"]["default_from"] == "repo_root"


def test_write_known_value_works_without_example(tmp_path):
    personal.write_known_value("demo", "USER_TAG", "lsh", home=tmp_path)
    data = yaml.safe_load((tmp_path / "projects" / "demo" / "personal.yaml").read_text(encoding="utf-8"))
    assert data["USER_TAG"] == "lsh"
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_personal_config.py -q`
Expected: FAIL，`AttributeError: module 'runtime.personal' has no attribute 'set_value'`。

- [ ] **Step 3: 实现**

- `KEY_DEFAULTS` 固定已知键的说明、类型与默认来源：`USER_TAG`、`REPO_PATH`、`REPORT_REPOS`、`JENKINS_USER`、`GIT_AUTHORS`、`ZENTAO_ACCOUNT`、`ZENTAO_AUTHORS`。
- `set_value`：读 `personal.example.yaml`；缺失时抛「缺少 personal.example.yaml，先运行 config example --write」。密钥键拒绝；未声明键在 `allow_unknown=False` 时拒绝。`type == "list"` 时按逗号拆分并去空白。合并已有 `personal.yaml`，用 `yaml.safe_dump(sort_keys=True, allow_unicode=True)` 原子写入。
- `set_secret`：键必须在 `.env.example`；`value.strip()` 为空拒绝；调用 `config.write_env_key`。
- `write_known_value`：工具内置键专用，不要求 example，合并写入 `personal.yaml`。
- `build_example`：扫描所有能力的占位符；在 `.env.example` 中的归密钥，其余归个人；已知键用 `KEY_DEFAULTS`，未知键用空说明、`string`、`none`。
- `write_example`：文件存在且 `force=False` 时返回 `None`；否则写 `{"version": 1, "keys": {...}}`。
- 原子写入辅助函数 `_atomic_write_text(path, text, private=False)`：同目录临时文件、`Path.replace`、POSIX 下 `chmod(0o600)`。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_personal_config.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 3 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 4: `scripts/config.py` 命令入口

**Files:**
- Create: `scripts/config.py`
- Test: `tests/test_config_cli.py`

**Interfaces:**
- Consumes: `personal.check`、`personal.report_json`、`personal.set_value`、`personal.set_secret`、`personal.write_example`
- Produces: `main(argv: list[str] | None = None) -> int`

**退出码：**

- `check` 无 `--capability`：缺失值不阻断（0）；`undeclared_variable`、`duplicate_declaration`、`missing_example` 为 2；任何 `invalid` 为 3。
- `check --capability`：缺失或任何漂移为 2；`invalid` 为 3；否则 0。
- `set`、`set-secret`、`example` 参数或配置错误为 2；成功为 0。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_config_cli.py`：

```python
def test_check_json_exit_2_when_capability_missing(home, capsys):
    code = config_cli.main(["--project", "demo", "check", "--capability", "git", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["capabilities"]["git"]["status"] == "missing"


def test_check_without_capability_does_not_fail_on_missing(home, capsys):
    assert config_cli.main(["--project", "demo", "check"]) == 0
    assert "USER_TAG" in capsys.readouterr().out


def test_set_writes_value(home, capsys):
    assert config_cli.main(["--project", "demo", "set", "USER_TAG=lsh"]) == 0
    assert "已写入 personal.yaml" in capsys.readouterr().out


def test_set_secret_never_prints_value(home, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("secret-value\n"))
    assert config_cli.main(["--project", "demo", "set-secret", "JENKINS_TOKEN"]) == 0
    out = capsys.readouterr().out
    assert "secret-value" not in out
    assert "JENKINS_TOKEN" in out


def test_example_write_creates_file(home, capsys):
    assert config_cli.main(["--project", "demo", "example", "--write"]) == 0
    assert (home / "projects" / "demo" / "personal.example.yaml").exists()


def test_invalid_yaml_exit_3(home, capsys):
    # jenkins.yaml 写坏
    assert config_cli.main(["--project", "demo", "check", "--capability", "jenkins"]) == 3
```

`home` fixture 与 Task 2 共用，放进 `tests/test_personal_config.py` 可导入，或在两个文件各建一份最小 fixture。它必须设置 `DATA_TOOLS_HOME`，并在项目目录声明 `USER_TAG`（personal example）与 `JENKINS_TOKEN`（`.env.example`）。

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config_cli.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.config'`。

- [ ] **Step 3: 实现 `scripts/config.py`**

- `sys.path.insert(0, parents[1])`；`sys.stdout.reconfigure(encoding="utf-8")`。
- argparse：`--project` 必填；子命令 `check`（`--capability` 选择 `personal.CAPABILITIES`、`--json`）、`set`（`pairs` nargs="+"、`--allow-unknown`）、`set-secret`（`key`）、`example`（`--write`）。
- `set` 解析 `KEY=VALUE`，按第一个 `=` 拆分；没有 `=` 返回 2。
- `set-secret`：`sys.stdin.isatty()` 时 `getpass.getpass`，否则读第一行；不打印值。
- `check` 人类输出按能力分组：`[git] ok`、`[jenkins] missing`，缺失项列出 `key（personal/secret）：description`，漂移列出 `文件: 说明`。
- `example` 除打印 `personal.example.yaml` 草稿外，还要打印「以下密钥键需要补进 .env.example：...」；`--write` 只写 personal example，不改 `.env.example`。
- 捕获 `personal.PersonalConfigError` 输出 `[配置] ...` 返回 2；`invalid` 状态返回 3。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config_cli.py tests/test_personal_config.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 4 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 5: Git 托管加载与 `set-user-tag`

**Files:**
- Modify: `runtime/git_host/config.py`
- Modify: `scripts/git_host.py`
- Test: `tests/test_git_host_config.py`、`tests/test_git_host_cli.py`

**Interfaces:**
- Consumes: `config.load_values`、`personal.write_known_value`
- Produces: `load_git_host_config` 支持 `${USER_TAG}`、`${REPO_PATH}`
- Produces: `save_user_tag(project_id, user_tag, home=None) -> None` 两种模式

- [ ] **Step 1: 写失败测试**

在 `tests/test_git_host_config.py` 追加：

```python
PLACEHOLDER_YAML = (
    "user_tag: ${USER_TAG}\nrepo_path: ${REPO_PATH}\n"
    "host: {kind: gitlab, base_url: http://g, project_path: a/b, token_key: T}\n"
)


def _placeholder_project(tmp_path):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(PLACEHOLDER_YAML, encoding="utf-8")
    return proj


def test_load_substitutes_personal_values(tmp_path):
    proj = _placeholder_project(tmp_path)
    (proj / "personal.yaml").write_text("USER_TAG: lsh\nREPO_PATH: C:/x\n", encoding="utf-8")
    cfg = load_git_host_config("demo", home=tmp_path)
    assert cfg.user_tag == "lsh"
    assert str(cfg.repo_path) == "C:/x"


def test_load_missing_personal_guides_setup(tmp_path):
    _placeholder_project(tmp_path)
    with pytest.raises(GitHostConfigError, match="project-setup"):
        load_git_host_config("demo", home=tmp_path)


def test_save_user_tag_writes_personal_in_placeholder_mode(tmp_path):
    proj = _placeholder_project(tmp_path)
    (proj / "personal.example.yaml").write_text(
        "version: 1\nkeys: {USER_TAG: {description: 标识}}\n", encoding="utf-8"
    )
    save_user_tag("demo", "zhang", home=tmp_path)
    assert yaml.safe_load((proj / "personal.yaml").read_text(encoding="utf-8"))["USER_TAG"] == "zhang"
    assert "${USER_TAG}" in (proj / "git_hosts.yaml").read_text(encoding="utf-8")


def test_save_user_tag_keeps_legacy_literal_mode(tmp_path):
    # 现有 test_save_user_tag_is_persisted 保持通过
```

在 `tests/test_git_host_cli.py` 追加一个占位符模式的 `project_config` fixture 和用例：共享 `user_tag: ${USER_TAG}` 时，`set-user-tag zhang` 返回 0，值写进 `personal.yaml`，共享文件不变。

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py tests/test_git_host_cli.py -q`
Expected: 新用例 FAIL；旧的 `save_user_tag` 用例仍 PASS。

- [ ] **Step 3: 实现**

`runtime/git_host/config.py`：

```python
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
try:
    data = config.substitute(data, config.load_values(_base(project_id, home)))
except config.ConfigError as exc:
    raise GitHostConfigError(f"git_hosts.yaml 变量解析失败：{exc}；缺少个人配置时先运行 project-setup") from exc
```

`save_user_tag`：

- 读取原始 YAML，取 `data.get("user_tag")`。
- 如果值等于 `"${USER_TAG}"`：调用 `personal.write_known_value(project_id, "USER_TAG", user_tag, home=home)`，不改共享文件。
- 否则：保持现有正则替换逻辑，就地更新共享文件。

`scripts/git_host.py::_set_user_tag`：

- 不再先 `load_git_host_config`（占位符缺值时会抛错，导致无法首次设置）。
- 直接读取 `config.project_dir(project) / "git_hosts.yaml"` 的原始 `user_tag`；文件不存在时按现有配置错误返回 2。
- `current` 非空且不等于 `${USER_TAG}` 时，保持「已存在，拒绝覆盖」返回 2。
- 否则调用 `save_user_tag`，打印 `user_tag: <tag>`，返回 0。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_git_host_config.py tests/test_git_host_cli.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 5 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 6: Jenkins 加载与 `setup`

**Files:**
- Modify: `runtime/jenkins/config.py`
- Modify: `scripts/jenkins.py`
- Test: `tests/test_jenkins_config.py`、`tests/test_jenkins_cli.py`

**Interfaces:**
- Consumes: `config.load_values`、`config.write_env_key`、`personal.write_known_value`
- Produces: `load_jenkins_config` 支持 `${JENKINS_USER}`
- Produces: `save_credentials(...) -> list[str]` 返回迁移警告

- [ ] **Step 1: 写失败测试**

追加：

```python
PLACEHOLDER_JENKINS = """
jenkins:
  base_url: http://jenkins.example.com
  user: ${JENKINS_USER}
  token_key: JENKINS_TOKEN
modules:
  order-service:
    paths: [order-service/]
    jobs: {dev: b2d-order-dev}
"""


def test_load_substitutes_personal_user(tmp_path):
    project = _write(tmp_path, PLACEHOLDER_JENKINS)
    (project / "personal.yaml").write_text("JENKINS_USER: liushihao\n", encoding="utf-8")
    cfg = load_jenkins_config("demo", home=tmp_path)
    assert cfg.user == "liushihao"


def test_save_credentials_placeholder_mode_writes_personal_and_preserves_shared(tmp_path):
    project = _write(tmp_path, PLACEHOLDER_JENKINS)
    warnings = save_credentials("demo", "http://jenkins.example.com", "liushihao", FAKE, home=tmp_path)
    data = yaml.safe_load((project / "jenkins.yaml").read_text(encoding="utf-8"))
    assert data["jenkins"]["user"] == "${JENKINS_USER}"
    assert data["modules"]
    assert yaml.safe_load((project / "personal.yaml").read_text(encoding="utf-8"))["JENKINS_USER"] == "liushihao"
    assert warnings == []


def test_save_credentials_legacy_literal_mode_updates_shared(tmp_path):
    project = _write(tmp_path, FULL_YAML)
    warnings = save_credentials("demo", "http://new.example.com", "newuser", FAKE, home=tmp_path)
    assert "${JENKINS_USER}" not in (project / "jenkins.yaml").read_text(encoding="utf-8")
    assert warnings and "占位符" in warnings[0]


def test_setup_placeholder_mode_writes_personal_and_env(home, fake, capsys):
    # home fixture 只创建 projects/demo；setup 会创建使用 ${JENKINS_USER} 的 jenkins.yaml
    code = _run(["setup", "--base-url", BASE, "--user", "liushihao"], fake, stdin=io.StringIO(FAKE))
    assert code == 0
    assert "JENKINS_USER: liushihao" in (home / "personal.yaml").read_text(encoding="utf-8")
    assert f"JENKINS_TOKEN={FAKE}" in (home / ".env").read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_jenkins_config.py tests/test_jenkins_cli.py -q`
Expected: 新用例 FAIL；旧的 `save_credentials` 用例仍 PASS。

- [ ] **Step 3: 实现**

`runtime/jenkins/config.py`：

- `load_jenkins_config`：`raw = yaml.safe_load(...)`；`data = config.substitute(raw, config.load_values(_base(project_id, home)))`，把 `config.ConfigError` 包成 `JenkinsConfigError`，消息含 `project-setup`。
- `save_credentials` 返回 `list[str]`：
  - 读现有 `jenkins.yaml`（可为空）。
  - 已有 `jenkins.user == "${JENKINS_USER}"` 或文件不存在：`personal.write_known_value(project_id, "JENKINS_USER", user, home=home)`；共享文件保留/写入 `user: ${JENKINS_USER}`；只在字段缺失时补 `base_url`、`token_key`、`baseline`、`modules`。
  - 已有 `jenkins.user` 是字面值：保持旧行为，写回 `data["jenkins"]["user"] = user`，返回一条警告「共享 jenkins.yaml 的 user 仍是字面值，建议改成 ${JENKINS_USER}」。
  - token 用 `config.write_env_key(project / ".env", token_key, token)`。
- 移除本文件里的 `_write_env_key`，改用 `config.write_env_key`。

`scripts/jenkins.py::_setup`：`warnings = save_credentials(...)`；逐条 `print`；其余不变。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_jenkins_config.py tests/test_jenkins_cli.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 6 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 7: 报告、造数、浏览器加载

**Files:**
- Modify: `runtime/report_config.py`
- Modify: `runtime/adapter.py`
- Modify: `runtime/browser/config.py`
- Modify: `scripts/browser.py`
- Test: `tests/test_report_config.py`、`tests/test_adapter.py`、`tests/test_browser_config.py`、`tests/test_browser_cli.py`

**Interfaces:**
- Consumes: `config.load_values`
- Produces: 四个加载器都从 `personal.yaml` + `.env` 取值
- Produces: `scripts/browser.py::_missing_browser_variables(project: str) -> list[str]`

- [ ] **Step 1: 写失败测试**

在 `tests/test_report_config.py`：

```python
def test_loads_personal_authors_and_repos(project):
    (project / "personal.yaml").write_text(
        "REPORT_REPOS: [C:/project/demo]\nGIT_AUTHORS: [liushihao, 刘师豪]\n",
        encoding="utf-8",
    )
    (project / "report.yaml").write_text(
        "git:\n  repos: ${REPORT_REPOS}\n  authors: ${GIT_AUTHORS}\n", encoding="utf-8"
    )
    cfg = load_report_config("demo")
    assert [p.name for p in cfg.git.repos] == ["demo"]
    assert cfg.git.authors == ["liushihao", "刘师豪"]
```

在 `tests/test_adapter.py`：

```python
def test_loads_value_from_personal_yaml(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL)
    (tmp_path / "projects/demo/.env").write_text("", encoding="utf-8")
    (tmp_path / "projects/demo/personal.yaml").write_text("BASE: http://personal\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert adapter.load_adapter("demo").envs["dev"]["base_url"] == "http://personal"
```

在 `tests/test_browser_config.py`：

```python
def test_personal_yaml_supplies_login_username(browser_project):
    (browser_project / ".env").write_text(
        "WEB=http://localhost\nAPI=http://localhost/api\nPASS=secret\n", encoding="utf-8"
    )
    (browser_project / "personal.yaml").write_text("USER: personal-admin\n", encoding="utf-8")
    cfg = load_browser_config("demo")
    assert cfg.login.username == "personal-admin"
```

在 `tests/test_browser_cli.py`：

```python
def test_missing_browser_variables_ignores_login_steps_builtins(browser_project):
    (browser_project / "personal.yaml").write_text("USER: u\n", encoding="utf-8")
    # .env 已有 WEB、API、PASS
    assert cli._missing_browser_variables("demo") == []
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report_config.py tests/test_adapter.py tests/test_browser_config.py tests/test_browser_cli.py -q`
Expected: 新用例 FAIL，值仍是 `.env` 里的旧值或报未定义变量。

- [ ] **Step 3: 实现**

- `runtime/report_config.py`：`config.load_env(base / ".env")` → `config.load_values(base)`。
- `runtime/adapter.py`：`config.load_env(base / ".env")` → `config.load_values(base)`；在调用处捕获 `config.ConfigError` 包成 `AdapterError`，消息含 `project-setup`。
- `runtime/browser/config.py`：`dotenv = load_env(...)` → `lookup = {**os.environ, **load_values(project_dir(project_id))}`；删除不再使用的 `load_env` 导入；捕获 `config.ConfigError` 包成 `BrowserConfigError`，消息含 `project-setup`。
- `scripts/browser.py`：
  - 导入 `load_values`，删除 `load_env`。
  - 抽出 `_missing_browser_variables(project: str) -> list[str]`：读 `browser/browser.yaml` 文本，`re.findall` 占位符，减去 `_RUNTIME_VARS`，再对照 `{**os.environ, **load_values(project_dir(project))}`。
  - `cmd_doctor` 用该函数填充「变量齐全」检查；捕获 `config.ConfigError`，把该项标为失败并显示「个人配置缺失或非法，运行 project-setup」。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report_config.py tests/test_adapter.py tests/test_browser_config.py tests/test_browser_cli.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 7 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 8: `project-setup` 技能与各技能接入

**Files:**
- Create: `skills/project-setup/SKILL.md`
- Modify: `skills/git-workflow/SKILL.md`、`skills/jenkins-deploy/SKILL.md`、`skills/report-writer/SKILL.md`、`skills/adapter-bootstrap/SKILL.md`、`skills/data-gen-core/SKILL.md`、`skills/db-access/SKILL.md`、`skills/browser-test/SKILL.md`
- Modify: `skills/_references/project-layout.md`、`skills/_references/trigger-routing.md`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: Task 4 的 `config.py` 命令
- Produces: 每个能力技能在 `## 前置检查` 里调用 `config.py check --capability <能力>`

- [ ] **Step 1: 写失败测试**

修改 `tests/test_skills.py`：

```python
SKILL_NAMES = [
    "data-gen-core", "db-access", "adapter-bootstrap", "report-writer",
    "git-workflow", "browser-test", "jenkins-deploy", "project-setup",
]


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_every_capability_skill_checks_personal_config(name):
    if name == "project-setup":
        return
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert "config.py" in text and "check" in text
    assert "project-setup" in text


def test_project_setup_skill_documents_flow():
    text = (SKILLS / "project-setup" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["config.py", "check", "set-secret", "personal.yaml", "不猜", "不回显"]:
        assert word in text
```

把现有的参数化列表扩展到 8 个技能；把 `test_trigger_routing_includes_jenkins` 里的「七个 skill」改为「八个 skill」；在 `test_trigger_routing_covers_all_intents` 的断言里加入 `"个人配置"` 和 `"project-setup"`。

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py -q`
Expected: FAIL，`project-setup/SKILL.md` 不存在或路由表仍是七个。

- [ ] **Step 3: 实现**

`skills/project-setup/SKILL.md` 必须有：

- frontmatter：`name: project-setup`，description 含触发词「初始化个人配置」「新同事接入」「配置我的账号」「配一下环境」「个人配置」。
- 标准 `## 第 0 步：环境检查`（与现有七个技能一致）。
- `## 适用场景`、`## 前置检查`、`## 执行`、`## 失败处理`。
- 执行步骤按 spec 第 7 节：`check --json` → 选能力 → 非敏感值用 `set` → 密钥打印 `set-secret` 终端命令 → 重新 `check` → 可选只读验证 → 汇总。
- 明确「不把密钥贴进对话」「不改共享 yaml」「缺共享配置时交维护人」。

七个能力技能在 `## 前置检查` 开头加同一段（命令单行）：

```markdown
运行 `<TOOLS_DIR>/.venv/Scripts/python.exe <TOOLS_DIR>/scripts/config.py --project <项目ID> check --capability <能力>`。有缺失时用 `project-setup` 补齐；不现场猜个人值，不修改共享 yaml；密钥只提示用户在自己的终端运行 `set-secret`。
```

能力映射：`git-workflow`→git，`jenkins-deploy`→jenkins，`report-writer`→report，`adapter-bootstrap`/`data-gen-core`/`db-access`→adapter，`browser-test`→browser。

`db-access` 的数据库凭据目前由 `adapter.yaml` 的 `db_prefix` 间接引用，`check --capability adapter` 只验证 `adapter.yaml` 里显式出现的 `${KEY}`；`DEV_HOST`、`DEV_PASSWORD` 这类键若没有在 `adapter.yaml` 中出现，仍由 `db-access` 现有的运行时错误提示补齐。本期不新增独立的 `db` 能力扫描。

同步修改：

- `git-workflow`：删除「询问 user_tag 后写共享文件」的旧表述，保留 `set-user-tag` 的说明并注明它写 `personal.yaml`。
- `jenkins-deploy`：首次流程区分「共享 jenkins.yaml 缺失 = 维护人任务」和「个人账号/token 缺失 = project-setup」；token 改为终端输入。
- `report-writer`：共享 report.yaml 缺失 = 维护人任务；个人值缺失 = project-setup。
- `adapter-bootstrap`/`browser-test`：新增 `${变量}` 时更新 `personal.example.yaml` 或 `.env.example`。
- `project-layout.md`：目录树加入 `personal.example.yaml`、`personal.yaml`；忽略列表加入 `personal.yaml`；新增「个人配置」小节。
- `trigger-routing.md`：首行「七个 skill」→「八个 skill」；表格加入「个人配置 → `project-setup`」。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py tests/test_install.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 8 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 9: 同步工具与 README

**Files:**
- Modify: `scripts/sync_project.py`
- Modify: `skills/_TEMPLATE/project-readme.md`
- Test: `tests/test_sync_project.py`

**Interfaces:**
- Produces: `PROJECT_DATA_FILES` 包含 `personal.yaml`、`personal.example.yaml`
- Produces: `GITIGNORE_BLOCK` 包含 `.data-tools/projects/*/personal.yaml`

- [ ] **Step 1: 写失败测试**

在 `tests/test_sync_project.py` 追加：

```python
def test_personal_files_are_project_data():
    from scripts.sync_project import PROJECT_DATA_FILES
    assert "personal.yaml" in PROJECT_DATA_FILES
    assert "personal.example.yaml" in PROJECT_DATA_FILES


def test_gitignore_ignores_personal_yaml(project):
    upsert_gitignore(project)
    text = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".data-tools/projects/*/personal.yaml" in text


def test_sync_preserves_personal_files(source, project):
    project_path = project / ".data-tools" / "projects" / "demo"
    project_path.mkdir(parents=True)
    (project_path / "personal.yaml").write_text("USER_TAG: lsh\n", encoding="utf-8")
    (project_path / "personal.example.yaml").write_text("version: 1\nkeys: {}\n", encoding="utf-8")
    result = sync_project(project, "demo", ("claude",), source)
    assert project_path / "personal.yaml" in result.preserved
    assert project_path / "personal.example.yaml" in result.preserved
    assert (project_path / "personal.yaml").read_text(encoding="utf-8") == "USER_TAG: lsh\n"
```

- [ ] **Step 2: 运行并确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

- `PROJECT_DATA_FILES` 追加 `"personal.yaml"`、`"personal.example.yaml"`。
- `GITIGNORE_BLOCK` 追加 `.data-tools/projects/*/personal.yaml`。
- `skills/_TEMPLATE/project-readme.md` 的「首次接入」改为：
  1. 运行 `bootstrap.ps1`。
  2. 在 AI 工具里说「初始化个人配置」，按提示生成 `personal.yaml` 和 `.env`。
  3. `personal.yaml`、`.env` 不提交，共享 yaml 不要写个人值。

- [ ] **Step 4: 运行并确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`
Expected: PASS。

- [ ] **Step 5: 检查点（不提交）**

记录 Task 9 的测试命令与结果；留到 Task 10 统一提交。

---

### Task 10: 文档、版本与全量验证

**Files:**
- Modify: `CONTRIBUTING.md`
- Modify: `docs/usage.md`
- Modify: `skills/_references/runtime-contract.md`
- Modify: `.claude-plugin/plugin.json`（由脚本生成，不手改）
- Test: `tests/test_version_sync.py`

**Interfaces:**
- Consumes: 前九个任务
- Produces: 版本 `1.9.0`

- [ ] **Step 1: 更新文档**

`CONTRIBUTING.md` 的「团队项目接入时的共享与本地边界」：

- 提交：`personal.example.yaml`、`.env.example`、共享 yaml（只含团队事实与 `${KEY}`）。
- 不提交：`personal.yaml`、`.env`。
- 加一句划分规则：身份、本机路径、个人账号、作者列表进个人；服务器地址、项目/产品 ID、模块映射、流程步骤留共享；密码令牌进 `.env`。

`docs/usage.md`：

- 「同事第一次接入」改为 bootstrap → 说「初始化个人配置」 → `project-setup` 问答 → 使用。
- Jenkins 段落把「jenkins.yaml 里只有地址和账号」改成「jenkins.yaml 只有地址与 `${JENKINS_USER}` 占位符；账号在本机 personal.yaml，token 在本机 .env」。
- 错误说明里补「缺个人配置 → 运行 project-setup」。

`skills/_references/runtime-contract.md`：在「项目内路径」后加一段「配置值来源」：`personal.yaml` + `.env` 合并，`.env` 优先；列表整值替换保留类型。

- [ ] **Step 2: 升版本**

Run: `.venv/Scripts/python.exe scripts/bump_version.py 1.9.0`
Expected: `.claude-plugin/plugin.json`、`.cursor-plugin/`、`.codex-plugin/` 清单同步为 `1.9.0`。

- [ ] **Step 3: 运行版本测试与敏感信息检查**

Run: `.venv/Scripts/python.exe -m pytest tests/test_version_sync.py -q`
Expected: PASS。

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`
Expected: `未发现敏感信息`。

- [ ] **Step 4: 全量测试**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 全部 PASS；若浏览器测试因本机 Chrome 跳过，记录跳过项，不视为失败。

- [ ] **Step 5: 一次性提交**

先看 `git status --short`，确认只有本次功能相关的文件。然后：

```bash
git add runtime scripts skills tests docs/superpowers CONTRIBUTING.md .claude-plugin .cursor-plugin .codex-plugin
git commit -m "feat: 个人配置分层与 project-setup 并升版本至 1.9.0"
```

按 Global Constraints：这是 Task 1-10 的唯一代码提交。

- [ ] **Step 6: 询问推送**

按 `AGENTS.md`：提交后询问使用者是否推送，不自行推送。

---

### Task 11: hexincloud 落地与验收

**Files:**
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/git_hosts.yaml`
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/jenkins.yaml`
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/report.yaml`
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/adapter.yaml`
- Modify: `C:/project/hexincloud/.data-tools/projects/hexincloud/browser/browser.yaml`
- Create: `C:/project/hexincloud/.data-tools/projects/hexincloud/personal.example.yaml`
- Create: `C:/project/hexincloud/.data-tools/projects/hexincloud/personal.yaml`（本机，不入库）

**说明：** 这是业务仓库的本地落地，不属于 claudeTool 的提交；是否提交 hexincloud 由使用者决定。

- [ ] **Step 1: 先同步新工具包**

在 claudeTool 运行：

```bash
.venv/Scripts/python.exe scripts/sync_project.py --project-dir C:/project/hexincloud --project-id hexincloud --targets claude --dry-run
```

确认输出包含 `data-tools/scripts/config.py`、`skills/project-setup`、新的 `.gitignore` 规则后，去掉 `--dry-run` 再跑一次。

- [ ] **Step 2: 替换共享配置里的个人值**

- `git_hosts.yaml`：`user_tag: ${USER_TAG}`、`repo_path: ${REPO_PATH}`。
- `jenkins.yaml`：`jenkins.user: ${JENKINS_USER}`。
- `report.yaml`：`git.repos: ${REPORT_REPOS}`、`git.authors: ${GIT_AUTHORS}`、`zentao.authors: ${ZENTAO_AUTHORS}`；团队共用的 `base_url` 改为字面值。
- `adapter.yaml` / `browser/browser.yaml`：团队地址改为字面值，个人账号改 `${...}`，密码令牌留在 `.env`（如 `WEB_USERNAME` 进 personal，`WEB_PASSWORD` 留 `.env`）。

- [ ] **Step 3: 生成个人键清单**

Run: `python C:/project/hexincloud/data-tools/scripts/config.py --project hexincloud example --write`
Expected: 生成 `personal.example.yaml`；按实际值补 `description`，确认密钥键都在 `.env.example`。

- [ ] **Step 4: 生成个人配置**

说「初始化个人配置」，由 `project-setup` 写入本机 `personal.yaml`；密钥用 `config.py set-secret` 在终端填写。

- [ ] **Step 5: 验收**

Run: `C:/project/hexincloud/data-tools/.venv/Scripts/python.exe C:/project/hexincloud/data-tools/scripts/config.py --project hexincloud check`
Expected: 所有能力 `ok`，无 `undeclared_variable`、`duplicate_declaration`、`literal_personal_value`。

Run: `git -C C:/project/hexincloud status --short`
Expected: 只出现共享 yaml、example 和同步产物；`personal.yaml`、`.env` 不出现。

Run: `C:/project/hexincloud/data-tools/.venv/Scripts/python.exe C:/project/hexincloud/data-tools/scripts/jenkins.py --project hexincloud modules --repo C:/project/hexincloud`
Expected: 正常输出分支、基线与命中模块；证明 `jenkins.yaml` 的 `${JENKINS_USER}` 已能从个人配置解析。记录实际输出。

- [ ] **Step 6: 提交决定**

把 `git status` 结果交给使用者，由使用者决定是否提交 hexincloud 的共享配置与 example；个人文件永不提交。
