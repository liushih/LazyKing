# 业务项目整包内置 data-tools 实现计划

> **2026-11-06 决策更新**：本计划的“整包内置并提交进业务仓库”已被取代。按合规与供应链要求，`data-tools/`、`.data-tools/` 和生成的技能入口一律不进业务仓库 git，只在本机安装；详见 [CONTRIBUTING.md](../../../CONTRIBUTING.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让业务仓库自带 `data-tools/` 与共享 `.data-tools/`，同事只需业务仓库和 Python 3.11+ 就能使用全部 5 项能力；不 pull 业务仓库时也能收到版本提示并一键更新。

**Architecture:** 同步工具把 claudeTool 的 `skills/`、`runtime/`、`scripts/` 复制进业务仓库，并以可移植方式渲染技能入口；运行时通过向上查找 `.data-tools/` 自动使用项目内数据根；bootstrap 检测 Python 并建 venv；update 通过远端 tag/commit 提示新版本，用户显式执行更新。

**Tech Stack:** Python 3.11+、PyYAML、pytest、PowerShell、git。

**Spec:** `docs/superpowers/specs/2026-11-02-project-embedded-data-tools-design.md`

## Global Constraints

- Python 3.11+；只支持 Python，不考虑 Java 等多语言。
- 不自动下载或静默安装 Python；缺失时打印 `https://www.python.org/downloads/` 并停止。
- 5 个技能全部覆盖：`db-access`、`data-gen-core`、`adapter-bootstrap`、`report-writer`、`git-workflow`。
- `data-tools/` 进业务仓库；`.data-tools/` 中 `adapter.yaml`、`pitfalls.md` 进仓库，`.env`、`ledger.csv`、`reports/` 不进。
- 生成技能入口时保留 `<TOOLS_DIR>` 占位符，不写本机绝对路径。
- Windows 优先；技能内同时兼容 POSIX 解释器路径。
- 更新必须显式执行；不静默覆盖代码，不自动 `git commit` / `git push`。
- 测试不得访问真实网络；git 与 subprocess 调用使用 mock 或本地临时仓库。
- 令牌、密码、私钥不出现在命令行、日志、台账、报告和测试数据中。

## Review Focus

1. 从业务仓库子目录启动 AI 工具时，`<DATA_HOME>` 必须找到最近的祖先 `.data-tools/`，而不是当前目录或用户目录。
2. 机器没有 Python 或版本低于 3.11 时，bootstrap 必须打印下载指引、退出码 1、不创建 `.venv`，不出现 Python 堆栈。
3. 重复执行 sync 时，已有 `adapter.yaml`、`pitfalls.md`、`.env` 内容不变，`.gitignore` 的 data-tools 块不重复。
4. `data-tools/` 有未提交改动时，update 必须在克隆和覆盖前拒绝，并提示先提交或暂存。
5. 更新检查遇到网络失败时，技能继续执行当前版本，不报错、不阻塞、不反复重试。

---

### Task 1: 项目内数据根解析

**Files:**
- Modify: `runtime/config.py:36-42`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `_find_up(name: str, start: Path | None = None) -> Path | None`
  - `data_home() -> Path`（优先级：`DATA_TOOLS_HOME` > 最近祖先 `.data-tools/` > `~/.data-tools`）
  - `project_dir(project_id: str) -> Path` 不变

- [ ] **Step 1: Write the failing tests**

在 `tests/test_config.py` 追加：

```python
def test_data_home_finds_project_local(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_TOOLS_HOME", raising=False)
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    monkeypatch.chdir(project)
    assert config.data_home() == (project / ".data-tools").resolve()


def test_data_home_finds_nearest_ancestor(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_TOOLS_HOME", raising=False)
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert config.data_home() == (project / ".data-tools").resolve()


def test_data_home_env_beats_project_local(monkeypatch, tmp_path):
    project = tmp_path / "repo"
    (project / ".data-tools").mkdir(parents=True)
    override = tmp_path / "override"
    override.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("DATA_TOOLS_HOME", str(override))
    assert config.data_home() == override
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`

Expected: 前两个新用例失败（当前 `data_home()` 只读环境变量和用户目录），第三个通过。

- [ ] **Step 3: Implement `_find_up` and update `data_home()`**

在 `runtime/config.py` 中实现：

```python
def _find_up(name: str, start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        candidate = parent / name
        if candidate.is_dir():
            return candidate
    return None


def data_home() -> Path:
    env = os.getenv("DATA_TOOLS_HOME")
    if env:
        return Path(env)
    local = _find_up(".data-tools")
    if local is not None:
        return local
    return Path.home() / ".data-tools"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add runtime/config.py tests/test_config.py
git commit -m "feat: 项目内 .data-tools 自动解析"
```

---

### Task 2: 可移植技能渲染

**Files:**
- Modify: `scripts/install.py:35-44`（`render`）
- Modify: `scripts/install.py:60-68`（`_codex_block`）
- Modify: `scripts/install.py:79-117`（`install`）
- Modify: `scripts/install.py:151-173`（CLI）
- Test: `tests/test_install.py`

**Interfaces:**
- Produces:
  - `render(tool: str, name: str, body: str, description: str, tools_dir: Path, portable: bool = False) -> str`
  - `install(targets: list[str], scope: str, project_dir, tools_dir: Path, home: Path, portable: bool = False) -> list[Path]`
  - CLI 新增 `--portable`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_install.py` 追加：

```python
def test_portable_render_keeps_placeholder(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["claude"], "project", repo, tools, home=tmp_path, portable=True)
    text = paths[0].read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" in text
    assert tools.as_posix() not in text


def test_portable_codex_block_points_to_project_tools(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, tools, home=tmp_path, portable=True)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "data-tools/skills" in text
    assert tools.as_posix() not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_install.py -q`

Expected: `portable` 参数不存在，测试报 `TypeError`。

- [ ] **Step 3: Implement portable rendering**

`render()` 增加参数 `portable: bool = False`，仅在 `not portable` 时替换 `<TOOLS_DIR>`：

```python
def render(tool: str, name: str, body: str, description: str, tools_dir: Path, portable: bool = False) -> str:
    if not portable:
        body = body.replace("<TOOLS_DIR>", Path(tools_dir).as_posix())
    ...
```

`_codex_block()` 增加 `portable` 参数；`portable=True` 时规则路径写 `data-tools/skills`，否则保持绝对路径。`install()` 增加 `portable` 参数并传给 `render` / `_codex_block`。CLI 增加 `--portable` 并传给 `install`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_install.py -q`

Expected: 全部通过，原有「`<TOOLS_DIR>` 被替换」的用例仍通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat: 技能渲染支持可移植路径"
```

---

### Task 3: 同步工具包与 VERSION

**Files:**
- Create: `scripts/sync_project.py`
- Test: `tests/test_sync_project.py`

**Interfaces:**
- Produces:
  - `TOOLKIT_ITEMS: tuple[str, ...]`
  - `DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"`
  - `class SyncResult`（`copied: list[Path]`、`rendered: list[Path]`、`preserved: list[Path]`）
  - `copy_toolkit(source_root: Path, project_dir: Path) -> list[Path]`
  - `write_version(source_root: Path, project_dir: Path, source_url: str = DEFAULT_SOURCE) -> Path`

- [ ] **Step 1: Write the failing tests**

创建 `tests/test_sync_project.py`：

```python
import pytest
import yaml

from scripts.sync_project import copy_toolkit, write_version


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"version": "1.4.0"}', encoding="utf-8")
    (root / "skills" / "db-access").mkdir(parents=True)
    (root / "skills" / "db-access" / "SKILL.md").write_text(
        "---\nname: db-access\ndescription: 测试\n---\n\n正文 <TOOLS_DIR>\n",
        encoding="utf-8",
    )
    (root / "skills" / "_TEMPLATE").mkdir()
    (root / "skills" / "_TEMPLATE" / "project-readme.md").write_text("# <PROJECT_ID>\n", encoding="utf-8")
    (root / "runtime").mkdir()
    (root / "runtime" / "__init__.py").write_text("", encoding="utf-8")
    (root / "runtime" / "__pycache__").mkdir()
    (root / "runtime" / "__pycache__" / "x.pyc").write_text("", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
    (root / "requirements.txt").write_text("PyYAML\n", encoding="utf-8")
    (root / "bootstrap.ps1").write_text("# bootstrap\n", encoding="utf-8")
    (root / "update.ps1").write_text("# update\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "x.py").write_text("", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("", encoding="utf-8")
    return root


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return path


def test_copy_toolkit_copies_whitelist_and_skips_caches(source, project):
    copied = copy_toolkit(source, project)
    dest = project / "data-tools"
    assert (dest / "skills" / "db-access" / "SKILL.md").exists()
    assert (dest / "requirements.txt").exists()
    assert (dest / "scripts" / "sync_project.py").exists()
    assert not (dest / ".venv").exists()
    assert not (dest / "__pycache__").exists()
    assert not (dest / "runtime" / "__pycache__").exists()
    assert all(path.exists() for path in copied)


def test_write_version_reads_plugin_version(source, project):
    path = write_version(source, project, "https://example.com/claudeTool.git")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["version"] == "1.4.0"
    assert data["source"] == "https://example.com/claudeTool.git"
    assert data["source_commit"] == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: `ModuleNotFoundError: scripts.sync_project`。

- [ ] **Step 3: Implement `scripts/sync_project.py` copy and version**

模块开头：

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

实现 `copy_toolkit()`：按 `TOOLKIT_ITEMS` 把 `source_root` 下的条目复制到 `project_dir / "data-tools"`，目录用 `shutil.copytree(..., dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv"))`，文件用 `shutil.copy2`。

实现 `write_version()`：从 `.claude-plugin/plugin.json` 读 `version`；用 `git -C <source> rev-parse --short HEAD` 取 commit，失败写 `"unknown"`；时间用 `datetime.now().astimezone().isoformat(timespec="seconds")`；写 YAML 到 `data-tools/VERSION`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_project.py tests/test_sync_project.py
git commit -m "feat: 同步工具包并写版本文件"
```

---

### Task 4: 渲染技能入口与 .gitignore

**Files:**
- Modify: `scripts/sync_project.py`
- Test: `tests/test_sync_project.py`

**Interfaces:**
- Produces:
  - `GITIGNORE_BEGIN = "# data-tools:begin"`
  - `GITIGNORE_END = "# data-tools:end"`
  - `render_targets(source_root: Path, project_dir: Path, targets: list[str]) -> list[Path]`
  - `upsert_gitignore(project_dir: Path) -> Path`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_sync_project.py` 追加：

```python
from scripts.sync_project import render_targets, upsert_gitignore


def test_render_targets_keeps_tools_dir_placeholder(source, project):
    paths = render_targets(source, project, ["claude"])
    text = (project / ".claude" / "skills" / "db-access" / "SKILL.md").read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" in text
    assert paths


def test_upsert_gitignore_is_idempotent(project):
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    upsert_gitignore(project)
    upsert_gitignore(project)
    text = (project / ".gitignore").read_text(encoding="utf-8")
    assert text.count("# data-tools:begin") == 1
    assert "node_modules/" in text
    assert "data-tools/.venv/" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: `ImportError`，两个函数未定义。

- [ ] **Step 3: Implement `render_targets` and `upsert_gitignore`**

`render_targets()` 调用 `scripts.install.install(targets, "project", project_dir, source_root, home=project_dir, portable=True)`，返回生成文件列表。

`upsert_gitignore()` 读写 `project_dir/.gitignore`，用 `re.sub` 删除旧块，再追加：

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_project.py tests/test_sync_project.py
git commit -m "feat: 渲染项目技能入口并维护 .gitignore"
```

---

### Task 5: 数据目录、项目 README 与 sync CLI

**Files:**
- Modify: `scripts/sync_project.py`
- Create: `skills/_TEMPLATE/project-readme.md`
- Test: `tests/test_sync_project.py`

**Interfaces:**
- Produces:
  - `init_data_dirs(project_dir: Path, project_id: str | None) -> list[Path]`
  - `render_project_readme(source_root: Path, project_dir: Path, project_id: str | None) -> Path`
  - `sync_project(project_dir: Path, project_id: str | None = None, targets: tuple[str, ...] = ("claude",), source_root: Path | None = None, source_url: str = DEFAULT_SOURCE, dry_run: bool = False) -> SyncResult`
  - CLI：`--project-dir`、`--project-id`、`--targets`、`--source`、`--source-url`、`--dry-run`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_sync_project.py` 追加：

```python
from scripts.sync_project import init_data_dirs, sync_project


def test_init_data_dirs_preserves_existing(source, project):
    project_path = project / ".data-tools" / "projects" / "demo"
    project_path.mkdir(parents=True)
    (project_path / "adapter.yaml").write_text("version: 1\n", encoding="utf-8")
    (project_path / "pitfalls.md").write_text("### P1\n", encoding="utf-8")
    (project_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    init_data_dirs(project, "demo")
    assert (project_path / "adapter.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert (project_path / "pitfalls.md").read_text(encoding="utf-8") == "### P1\n"
    assert (project_path / ".env").read_text(encoding="utf-8") == "SECRET=1\n"
    assert (project_path / ".env.example").exists()
    assert "default_project: demo" in (project / ".data-tools" / "config.yaml").read_text(encoding="utf-8")


def test_sync_project_end_to_end(source, project):
    result = sync_project(project, "demo", ("claude",), source)
    assert (project / "data-tools" / "VERSION").exists()
    assert (project / ".claude" / "skills" / "db-access" / "SKILL.md").exists()
    assert (project / "data-tools" / "README.md").exists()
    assert (project / ".gitignore").exists()
    assert result.copied


def test_sync_project_dry_run_writes_nothing(source, project):
    sync_project(project, "demo", ("claude",), source, dry_run=True)
    assert not (project / "data-tools").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: `ImportError` / 函数未定义。

- [ ] **Step 3: Implement `init_data_dirs`**

`init_data_dirs()`：

- 创建 `.data-tools/` 与 `.data-tools/projects/<id>/`。
- `config.yaml` 不存在时写 `default_project: <id>`；存在但没有该键时追加，不覆盖其他内容。
- `.env.example` 不存在时写注释模板；不覆盖已有 `.env`、`adapter.yaml`、`pitfalls.md`、`report.yaml`、`git_hosts.yaml`。

- [ ] **Step 4: Create README template and `render_project_readme`**

创建 `skills/_TEMPLATE/project-readme.md`，至少包含：

```markdown
# <PROJECT_ID> data-tools

本目录由 claudeTool 同步生成，不要手改。

## 首次接入

1. 确认本机有 Python 3.11+（没有则到 https://www.python.org/downloads/ 下载安装，勾选 Add to PATH）。
2. 在业务仓库根目录运行 `powershell -ExecutionPolicy Bypass -File data-tools/bootstrap.ps1`。
3. 复制 `.data-tools/projects/<PROJECT_ID>/.env.example` 为 `.env`，填入账号。
4. 打开 AI 工具，直接说「造 100 张 <业务对象>」。

## 更新

`powershell -ExecutionPolicy Bypass -File data-tools/update.ps1`
```

`render_project_readme()` 读取模板，替换 `<PROJECT_ID>`，写 `data-tools/README.md`。

- [ ] **Step 5: Implement `sync_project` orchestration and CLI**

`sync_project()` 依次调用：`copy_toolkit`、`write_version`、`render_targets`、`init_data_dirs`、`render_project_readme`、`upsert_gitignore`。`dry_run=True` 时把将要复制/渲染的路径打印出来，返回 `SyncResult`，不创建任何文件。

CLI 用 `argparse`，`--source` 默认 `Path(__file__).resolve().parents[1]`；捕获 `FileNotFoundError` / `ValueError`，打印到 stderr，返回 2。

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sync_project.py -q`

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add scripts/sync_project.py skills/_TEMPLATE/project-readme.md tests/test_sync_project.py
git commit -m "feat: 同步数据目录与项目 README"
```

---

### Task 6: 版本比较与检查缓存

**Files:**
- Create: `scripts/update.py`
- Test: `tests/test_update.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"`
  - `DEFAULT_INTERVAL_HOURS = 24`
  - `class Version`（`major`、`minor`、`patch`；可比较）
  - `parse_version(text: str) -> Version | None`
  - `is_newer(local: str, remote: str) -> bool`
  - `read_local_version(project_dir: Path) -> dict`
  - `load_settings(project_dir: Path) -> dict`（`source`、`update_check`、`check_interval_hours`）
  - `read_cache(project_dir: Path) -> dict`
  - `write_cache(project_dir: Path, latest_version: str | None, latest_commit: str | None, now: datetime) -> None`
  - `cache_is_fresh(cache: dict, now: datetime, hours: int) -> bool`

- [ ] **Step 1: Write the failing tests**

创建 `tests/test_update.py`：

```python
from datetime import datetime, timedelta, timezone

from scripts.update import (
    Version,
    cache_is_fresh,
    is_newer,
    parse_version,
    read_cache,
    write_cache,
)


def test_parse_version_accepts_v_prefix():
    assert parse_version("v1.4.0") == Version(1, 4, 0)


def test_is_newer_compares_numerically():
    assert is_newer("1.9.0", "1.10.0") is True
    assert is_newer("1.10.0", "1.9.0") is False


def test_cache_round_trip(tmp_path):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    write_cache(tmp_path, "1.5.0", "abc1234", now)
    cache = read_cache(tmp_path)
    assert cache["latest_version"] == "1.5.0"
    assert cache_is_fresh(cache, now + timedelta(hours=1), 24) is True
    assert cache_is_fresh(cache, now + timedelta(hours=25), 24) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: `ModuleNotFoundError: scripts.update`。

- [ ] **Step 3: Implement version and cache functions**

`Version` 用 `@dataclass(frozen=True, order=True)`。`parse_version` 只接受 `v?X.Y.Z`。`is_newer` 在任一侧解析失败时返回 `False`。

`read_local_version` 读 `data-tools/VERSION` YAML。`load_settings` 读 `.data-tools/config.yaml` 的 `data_tools` 段，缺省值：`source=DEFAULT_SOURCE`、`update_check=True`、`check_interval_hours=24`。

缓存路径 `.data-tools/.update-check.json`，内容包含 `last_checked`、`latest_version`、`latest_commit`。`cache_is_fresh` 用 `datetime.fromisoformat`，无法解析返回 `False`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/update.py tests/test_update.py
git commit -m "feat: 版本比较与更新检查缓存"
```

---

### Task 7: 更新检查与 CLI

**Files:**
- Modify: `scripts/update.py`
- Test: `tests/test_update.py`

**Interfaces:**
- Produces:
  - `class UpdateError(Exception)`
  - `class CheckResult`（`available: bool`、`local: str`、`remote: str | None`、`message: str`）
  - `remote_versions(source: str) -> list[Version]`
  - `remote_head(source: str) -> str | None`
  - `check_update(project_dir: Path, source: str | None = None, now: datetime | None = None) -> CheckResult`
  - CLI：`--project-dir`、`--source`、`--check`、`--quiet`；检查模式有新版本时退出码 10

- [ ] **Step 1: Write the failing tests**

在 `tests/test_update.py` 顶部补 `import subprocess` 和 `from pathlib import Path`，然后追加：

```python
import pytest

from scripts import update


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    return path


def _write_version(project, version="1.4.0", commit="aaa1111"):
    path = project / "data-tools"
    path.mkdir(parents=True, exist_ok=True)
    (path / "VERSION").write_text(
        f"version: {version}\nsource_commit: {commit}\n", encoding="utf-8"
    )


def test_check_update_reports_new_tag(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "remote_versions", lambda source: [update.Version(1, 4, 0), update.Version(1, 5, 0)])
    monkeypatch.setattr(update, "remote_head", lambda source: None)
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is True
    assert "v1.5.0" in result.message


def test_check_update_uses_fresh_cache_without_network(project, monkeypatch):
    _write_version(project)
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    update.write_cache(project, "1.5.0", None, now)
    monkeypatch.setattr(
        update, "remote_versions",
        lambda source: (_ for _ in ()).throw(AssertionError("network")),
    )
    result = update.check_update(project, source="https://example.com/repo.git", now=now)
    assert result.available is True


def test_check_update_swallows_network_error(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(
        update, "remote_versions",
        lambda source: (_ for _ in ()).throw(update.UpdateError("offline")),
    )
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is False


def test_check_update_uses_commit_when_no_tags(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "remote_versions", lambda source: [])
    monkeypatch.setattr(update, "remote_head", lambda source: "bbb2222")
    result = update.check_update(project, source="https://example.com/repo.git")
    assert result.available is True
    assert "main@bbb2222" in result.message


def test_cli_check_returns_10_when_update_available(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(
        update, "check_update",
        lambda project_dir, source=None, now=None: update.CheckResult(
            True, "1.4.0", "1.5.0", "有新版本"
        ),
    )
    assert update.main(["--project-dir", str(project), "--check", "--quiet"]) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: `check_update` 未定义。

- [ ] **Step 3: Implement check and CLI**

`remote_versions()` 执行 `git ls-remote --tags --refs <source> "v*"`，解析每行最后一个 `/` 后的 tag，转成 `Version` 列表。`remote_head()` 执行 `git ls-remote <source> refs/heads/main`，取第一列的短 SHA。

`check_update()`：

1. 读本地 `VERSION` 和设置；`update_check` 为 false 时直接返回不可用。
2. 缓存新鲜时用缓存结果，不联网：semver 高于本地，或 `latest_commit` 与本地 `source_commit` 不同，均视为有更新。
3. 否则取远端最高 tag；没有 tag 时比较 `remote_head` 与本地 `source_commit`。
4. 有更新时 `message = f"[data-tools] 本地 v{local}，远端 v{remote}。运行 data-tools/update.ps1 更新。"`。
5. 网络异常（`UpdateError`、`subprocess.TimeoutExpired`、`OSError`）写空缓存并返回不可用。
6. 写缓存。

CLI 的 `--check` 模式：打印 `message`（`--quiet` 且无更新时不打印），有新版本返回 10，否则 0。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/update.py tests/test_update.py
git commit -m "feat: 检查远端版本并提示更新"
```

---

### Task 8: 执行更新与脏工作区保护

**Files:**
- Modify: `scripts/update.py`
- Test: `tests/test_update.py`

**Interfaces:**
- Produces:
  - `apply_update(project_dir: Path, source: str | None = None) -> int`
  - `_dirty_toolkit(project_dir: Path) -> bool`
  - `_default_project(project_dir: Path) -> str | None`
  - `_targets(project_dir: Path) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_update.py` 追加：

```python
def test_apply_update_refuses_dirty_toolkit(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_dirty_toolkit", lambda path: True)
    with pytest.raises(update.UpdateError, match="未提交"):
        update.apply_update(project, source="https://example.com/repo.git")


def test_apply_update_clones_and_syncs(project, monkeypatch):
    _write_version(project)
    monkeypatch.setattr(update, "_dirty_toolkit", lambda path: False)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            clone = Path(cmd[-1])
            (clone / ".claude-plugin").mkdir(parents=True)
            (clone / ".claude-plugin" / "plugin.json").write_text(
                '{"version": "1.5.0"}', encoding="utf-8"
            )
            (clone / "scripts").mkdir()
            (clone / "scripts" / "sync_project.py").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(update.subprocess, "run", fake_run)
    assert update.apply_update(project, source="https://example.com/repo.git") == 0
    assert any("sync_project.py" in " ".join(call) for call in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: `apply_update` 未定义。

- [ ] **Step 3: Implement `_dirty_toolkit` and the dirty guard**

`_dirty_toolkit()` 执行 `git -C <project> status --porcelain -- data-tools`；有输出返回 `True`。不是 git 仓库时返回 `False` 并打印警告。`apply_update()` 一开始调用它，为真时抛 `UpdateError("data-tools 有未提交改动，请先提交或暂存后再更新")`。

- [ ] **Step 4: Implement clone and sync in `apply_update`**

`apply_update()`：

1. 读本地 `VERSION` 和设置；没有 `data-tools/` 时抛 `UpdateError`。
2. 用 `tempfile.TemporaryDirectory()` 浅克隆源：`git clone --depth 1 <source> <temp>/clone`。
3. 读克隆里的 `.claude-plugin/plugin.json` 版本和 `git -C <clone> rev-parse --short HEAD`；版本不高于本地且 commit 与本地 `source_commit` 相同才提示「已是最新」并返回 0。
4. 用克隆里的 `scripts/sync_project.py` 同步；`project_id` 非空时才加 `--project-id`：`[sys.executable, str(clone / "scripts" / "sync_project.py"), "--project-dir", str(project_dir), *(["--project-id", project_id] if project_id else []), "--targets", ",".join(targets)]`。
5. 打印「已更新到 vX；请在业务仓库提交 data-tools/ 的变更」，返回 0。

- [ ] **Step 5: Implement `_default_project`, `_targets`, and CLI**

`_default_project()` 读 `.data-tools/config.yaml` 的 `default_project`。`_targets()` 按已存在的目录推断：`.claude/skills` → claude、`.cursor/rules` → cursor、`AGENTS.md` → codex、`.dsh/skills` → dsh；默认 `("claude",)`。

CLI 不带 `--check` 时调用 `apply_update`，捕获 `UpdateError` 打印并返回 1。

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_update.py -q`

Expected: 全部通过。

- [ ] **Step 7: Commit**

```bash
git add scripts/update.py tests/test_update.py
git commit -m "feat: 执行 data-tools 更新并保护脏工作区"
```

---

### Task 9: PowerShell 包装脚本

**Files:**
- Create: `bootstrap.ps1`
- Create: `update.ps1`
- Test: `tests/test_bootstrap.py`

**Interfaces:**
- `bootstrap.ps1` 参数：`-ProjectId <string>`、`-CheckOnly`、`-PythonCommand <string>`（测试用，默认自动探测）
- `update.ps1` 参数：`-CheckOnly`、`-Quiet`、`-PythonCommand <string>`

- [ ] **Step 1: Write the failing tests**

创建 `tests/test_bootstrap.py`：

```python
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.fixture
def tools_dir(tmp_path):
    tools = tmp_path / "repo" / "data-tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "bootstrap.ps1", tools / "bootstrap.ps1")
    return tools


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_bootstrap_missing_python_prints_download(tools_dir):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-CheckOnly", "-PythonCommand", "definitely-not-python"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "https://www.python.org/downloads/" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_bootstrap_check_only_without_venv_exits_2(tools_dir):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools_dir / "bootstrap.ps1"), "-CheckOnly", "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not available")
def test_update_ps1_passes_check_exit_code(tmp_path):
    tools = tmp_path / "repo" / "data-tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "update.ps1", tools / "update.ps1")
    (tools / "scripts").mkdir()
    (tools / "scripts" / "update.py").write_text("import sys; sys.exit(10)\n", encoding="utf-8")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(tools / "update.ps1"), "-CheckOnly", "-Quiet", "-PythonCommand", sys.executable],
        capture_output=True, text=True,
    )
    assert result.returncode == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py -q`

Expected: `FileNotFoundError: bootstrap.ps1`。

- [ ] **Step 3: Implement `bootstrap.ps1` and `update.ps1`**

`bootstrap.ps1`：

- `$tools = $PSScriptRoot`，`$root = Split-Path $tools -Parent`。
- 检测顺序：`$tools/.venv/Scripts/python.exe` → `-PythonCommand` → `py -3.11` → `py -3` → `python` → `python3`。指定 `-PythonCommand` 时只使用该命令，不再回退其他候选（测试用）。
- 解析 `--version` 输出，要求 `>= 3.11`。
- 缺失/过低：打印下载地址，`exit 1`。
- `-CheckOnly`：无 `.venv` 退出 2，有则退出 0。
- 正常模式：创建 `.venv`、升级 pip、安装 `requirements.txt`；`-ProjectId` 时创建 `.data-tools/projects/<id>/`。

`update.ps1`：

- 用同样的解释器探测（优先 `.venv`）。
- 把 `-CheckOnly` / `-Quiet` 转成 `--check` / `--quiet`，调用 `$tools/scripts/update.py --project-dir $root`。
- 透传退出码。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_bootstrap.py -q`

Expected: 通过；没有 PowerShell 时跳过。

- [ ] **Step 5: Commit**

```bash
git add bootstrap.ps1 update.ps1 tests/test_bootstrap.py
git commit -m "feat: 增加 Python 检测与更新入口脚本"
```

---

### Task 10: 5 个技能的环境前置与路径说明

**Files:**
- Create: `skills/_references/project-layout.md`
- Modify: `skills/db-access/SKILL.md`（在 `## 前置检查` 前插入）
- Modify: `skills/data-gen-core/SKILL.md`（同上）
- Modify: `skills/adapter-bootstrap/SKILL.md`（同上）
- Modify: `skills/report-writer/SKILL.md`（同上）
- Modify: `skills/git-workflow/SKILL.md`（同上）
- Modify: `skills/_references/runtime-contract.md`
- Test: `tests/test_skills.py`

**Interfaces:**
- 每个 `SKILL.md` 新增 `## 第 0 步：环境检查`，并替换 `## 路径` 段。

- [ ] **Step 1: Write the failing test**

在 `tests/test_skills.py` 追加：

```python
@pytest.mark.parametrize("name", ["data-gen-core", "db-access", "adapter-bootstrap", "report-writer", "git-workflow"])
def test_skill_has_environment_preflight(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert "## 第 0 步：环境检查" in text
    assert "Python 3.11+" in text
    assert "bootstrap.ps1" in text
    assert "update.ps1 -CheckOnly -Quiet" in text
    assert "data-tools/" in text
    assert (SKILLS / "_references" / "project-layout.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py::test_skill_has_environment_preflight -q`

Expected: 5 个用例全部失败。

- [ ] **Step 3: Add the preflight block and update paths**

在每个 `SKILL.md` 的 `## 前置检查` 前插入：

```markdown
## 第 0 步：环境检查

1. 定位 <TOOLS_DIR>：从当前目录向上查找 data-tools/；找不到读 DATA_TOOLS_DIR；仍找不到再读 ~/.data-tools/config.yaml 的 tools_dir；仍找不到就问用户业务仓库根目录，不猜。
2. 定位 <DATA_HOME>：先读 DATA_TOOLS_HOME；没有再从当前目录向上查找 .data-tools/；仍找不到用 ~/.data-tools。
3. 解释器优先 <TOOLS_DIR>/.venv/Scripts/python.exe（Windows）或 <TOOLS_DIR>/.venv/bin/python（POSIX）。
4. 没有 venv 时检查 py -3.11 --version / py -3 --version / python --version / python3 --version，要求 Python 3.11+。
5. 都没有或版本过低：提示用户到 https://www.python.org/downloads/ 下载安装 Python 3.11+，勾选 Add to PATH；停止，不代装。
6. 有 Python 但没 venv：运行 <TOOLS_DIR>/bootstrap.ps1。
7. 运行 <TOOLS_DIR>/update.ps1 -CheckOnly -Quiet：有新版本就把提示原样告诉用户，不自动更新；脚本不存在、无新版本或检查失败则继续。
```

把每个文件的 `## 路径` 段替换为：

```markdown
命令里的 `<TOOLS_DIR>` 是业务仓库根目录下的 `data-tools/`：从当前目录向上查找；找不到再读 `DATA_TOOLS_DIR`；仍找不到再读 `~/.data-tools/config.yaml` 的 `tools_dir`；仍找不到就问用户业务仓库根目录，不要猜。`<DATA_HOME>` 是业务仓库根目录下的 `.data-tools/`：先读 `DATA_TOOLS_HOME`，没有再从当前目录向上查找，最后回退 `~/.data-tools`。

解释器优先 `<TOOLS_DIR>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（POSIX）；没有 venv 时用 `py -3.11` / `py -3` / `python` / `python3`，要求 3.11+；有 Python 但没 venv 时运行 `<TOOLS_DIR>/bootstrap.ps1`。
```

创建 `skills/_references/project-layout.md`，写清上述路径、Python 检查、bootstrap、update 的细节。`runtime-contract.md` 增加「项目内路径」一节，说明 `<TOOLS_DIR>` / `<DATA_HOME>` 的解析。

`adapter-bootstrap` 额外说明：接入完成后同时维护 `.env.example` 的键名，不写值。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_skills.py -q`

Expected: 全部通过，原有断言不回归。

- [ ] **Step 5: Commit**

```bash
git add skills tests/test_skills.py
git commit -m "feat: 5 个技能增加项目内环境前置"
```

---

### Task 11: 文档

**Files:**
- Modify: `README.md`
- Modify: `docs/usage.md`

- [ ] **Step 1: Add team project section to README**

在「快速开始」后新增「团队项目接入（整包内置）」：

````markdown
## 团队项目接入（整包内置）

维护者在 claudeTool 仓库执行：

```bash
python scripts/sync_project.py --project-dir C:\project\<业务仓库> --project-id <项目ID> --targets claude
```

业务仓库会新增 `data-tools/`、`.claude/skills/`、`.data-tools/`。同事只需：

1. clone 业务仓库
2. 跑 `data-tools/bootstrap.ps1`（没有 Python 会提示下载）
3. 复制 `.data-tools/projects/<项目ID>/.env.example` 为 `.env`
4. 直接说「造 100 张提货单」

更新：`data-tools/update.ps1`。个人全局使用仍可用插件市场，互不影响。
````

- [ ] **Step 2: Add usage section**

在 `docs/usage.md` 增加「十二、团队项目接入」：目录布局、bootstrap、更新、常见问题（Python 缺失、data-tools 脏、网络不可达）。

- [ ] **Step 3: Verify links and commands**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: 全部通过。

- [ ] **Step 4: Commit**

```bash
git add README.md docs/usage.md
git commit -m "docs: 补充团队项目接入说明"
```

---

### Task 12: 端到端验收

**Files:**
- No code changes.

以下 PowerShell 步骤在同一会话连续执行；分开执行时，每步先设置 `$tmp = Join-Path $env:TEMP "data-tools-e2e"`。

- [ ] **Step 1: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: 全部通过。

- [ ] **Step 2: Run secret scan**

Run: `.venv/Scripts/python.exe scripts/check_secrets.py`

Expected: 无明文凭据、令牌、私钥、私网地址告警。

- [ ] **Step 3: Sync into a temporary business repo**

PowerShell：

```powershell
$tmp = Join-Path $env:TEMP "data-tools-e2e"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
.venv/Scripts/python.exe scripts/sync_project.py --project-dir $tmp --project-id demo --targets claude
```

Expected: `$tmp/data-tools/`、`$tmp/.claude/skills/`、`$tmp/.data-tools/projects/demo/` 均存在。

- [ ] **Step 4: Verify bootstrap check modes**

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File "$tmp/data-tools/bootstrap.ps1" -CheckOnly
```

Expected: 没有 `.venv` 时退出码 2；打印 Python 可用信息，不创建文件。

- [ ] **Step 5: Verify update check is non-blocking**

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File "$tmp/data-tools/update.ps1" -CheckOnly -Quiet
```

Expected: 退出码 0（无新版本/网络不可达）或 10（有新版本）；不产生异常堆栈，不阻塞。

- [ ] **Step 6: Verify generated skill paths**

检查 `$tmp/.claude/skills/db-access/SKILL.md`：

Expected: 包含 `<TOOLS_DIR>` 占位符，且不包含本机 claudeTool 绝对路径；包含「第 0 步：环境检查」。

- [ ] **Step 7: Clean up**

PowerShell：

```powershell
Remove-Item -Recurse -Force $tmp
```

- [ ] **Step 8: Commit final state if any files changed**

```bash
git status
```

Expected: 只有计划内文件变更；如无变更则跳过提交。
