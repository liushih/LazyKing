"""把工具包同步到业务仓库的本机副本：按白名单复制到 data-tools/ 并写入 VERSION。

所有产物只在本机使用，不进入业务仓库的 git；同步时会补齐 .gitignore 整目录规则。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PureWindowsPath

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.install import BEGIN, END, install, skill_names

DEFAULT_SOURCE = "https://github.com/liushih/claudeTool.git"

GITIGNORE_BEGIN = "# data-tools:begin"
GITIGNORE_END = "# data-tools:end"
GITIGNORE_HEADER = "# data-tools 只在本机使用，不进入业务仓库的 git"

# 团队模式只生成这些入口；codex 只能写 AGENTS.md，无法局部忽略，因此不支持。
ALLOWED_TARGETS: tuple[str, ...] = ("claude", "cursor", "dsh")

# 旧版本曾随工具包分发、现已废弃的本机文件，同步时顺手清掉。
OBSOLETE_TOOLKIT_FILES: tuple[str, ...] = (
    "scripts/track_shared.py",
    "runtime/track_shared.py",
)


def gitignore_block(names: list[str]) -> str:
    """生成业务仓库 .gitignore 的 data-tools 块：整目录忽略，不依赖逐文件规则。"""
    lines = [
        GITIGNORE_BEGIN,
        GITIGNORE_HEADER,
        "/data-tools/",
        "/.data-tools/",
    ]
    for name in names:
        lines.append(f"/.claude/skills/{name}/")
        lines.append(f"/.cursor/rules/{name}.mdc")
        lines.append(f"/.dsh/skills/{name}/")
    lines.append(GITIGNORE_END)
    return "\n".join(lines) + "\n"

TOOLKIT_ITEMS: tuple[str, ...] = (
    "skills",
    "runtime",
    "scripts",
    "requirements.txt",
    "bootstrap.ps1",
    "update.ps1",
    "LICENSE",
)

# 工具包必须存在这些条目才能同步；bootstrap.ps1 / update.ps1 由后续任务补齐，保持宽松。
CORE_ITEMS: tuple[str, ...] = ("skills", "runtime", "scripts", "requirements.txt")

# 项目数据目录里由人维护、同步时绝不覆盖的文件。
PROJECT_DATA_FILES: tuple[str, ...] = (
    "adapter.yaml",
    "pitfalls.md",
    "report.yaml",
    "git_hosts.yaml",
    "jenkins.yaml",
    "personal.yaml",
    "personal.example.yaml",
    ".env",
)

ENV_EXAMPLE_TEMPLATE = """# 复制为 .env 后填写，键名与 adapter.yaml 中的 ${变量} 对应
# 示例：
# DEV_HOST=
# DEV_PORT=
# DEV_USER=
# DEV_PASSWORD=
# TEST_HOST=
# TEST_PORT=
# TEST_USER=
# TEST_PASSWORD=
# 使用 Jenkins 发版时，token 由 jenkins.py setup 写入：
# JENKINS_TOKEN=
"""

IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")


@dataclass
class SyncResult:
    copied: list[Path] = field(default_factory=list)
    rendered: list[Path] = field(default_factory=list)
    preserved: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    cleaned: list[Path] = field(default_factory=list)


def copy_toolkit(source_root: Path, project_dir: Path) -> list[Path]:
    """把白名单条目从 source_root 复制到 project_dir/data-tools，返回复制后的路径。"""
    dest_root = project_dir / "data-tools"
    copied: list[Path] = []
    for item in TOOLKIT_ITEMS:
        src = source_root / item
        if not src.exists():
            continue
        dest = dest_root / item
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=IGNORE_PATTERNS)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        copied.append(dest)
    return copied


def remove_obsolete_toolkit_files(project_dir: Path) -> list[Path]:
    """删除旧版本留在本机副本里的废弃文件；不碰业务数据。"""
    removed: list[Path] = []
    for rel in OBSOLETE_TOOLKIT_FILES:
        path = Path(project_dir) / "data-tools" / rel
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def remove_agents_block(project_dir: Path) -> Path | None:
    """删除 AGENTS.md 中的 data-tools 块；文件只剩该块时一并删除。"""
    path = Path(project_dir) / "AGENTS.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    updated = re.sub(rf"{re.escape(BEGIN)}.*?{re.escape(END)}\n?", "", text, flags=re.S)
    if updated == text:
        return None
    if updated.strip():
        path.write_text(updated.rstrip() + "\n", encoding="utf-8")
    else:
        path.unlink()
    return path


def _validate_targets(targets: tuple[str, ...]) -> None:
    if "codex" in targets:
        raise ValueError(
            "团队模式不生成 codex 入口：codex 只能写入业务仓库的 AGENTS.md，"
            "无法在不污染业务仓库 git 的前提下使用；请改用 claude/cursor/dsh，"
            "或使用个人全局安装并自行确保 AGENTS.md 不提交。"
        )
    unknown = [name for name in targets if name not in ALLOWED_TARGETS]
    if unknown:
        raise ValueError(
            f"未知工具 {', '.join(unknown)}（可选：{', '.join(ALLOWED_TARGETS)}）"
        )


def _tracked_data_tools_paths(project_dir: Path, names: list[str]) -> list[str]:
    """返回已被 git 跟踪的 data-tools 相关路径，用于迁移提示。"""
    project_dir = Path(project_dir)
    if not (project_dir / ".git").exists():
        return []
    roots = ["data-tools", ".data-tools"]
    roots.extend(f".claude/skills/{name}" for name in names)
    roots.extend(f".cursor/rules/{name}.mdc" for name in names)
    roots.extend(f".dsh/skills/{name}" for name in names)
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir), "ls-files", "--", *roots],
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def warn_if_tracked(project_dir: Path, names: list[str]) -> None:
    """已有业务仓库可能提交过旧版本；提示如何把这些路径移出版本库。"""
    tracked = _tracked_data_tools_paths(project_dir, names)
    if not tracked:
        return
    roots = ["data-tools", ".data-tools"]
    roots.extend(f".claude/skills/{name}" for name in names)
    roots.extend(f".cursor/rules/{name}.mdc" for name in names)
    roots.extend(f".dsh/skills/{name}" for name in names)
    roots = [
        root
        for root in roots
        if any(path == root or path.startswith(root + "/") for path in tracked)
    ]
    print(
        "[data-tools] 以下路径已被 git 跟踪，但按策略不应进入业务仓库：\n  "
        + "\n  ".join(tracked)
        + "\n本地文件会保留。请运行：\n  git rm -r --cached -- "
        + " ".join(roots)
        + "\n然后提交这次删除。",
        file=sys.stderr,
    )


def _source_commit(source_root: Path) -> str:
    # 只认 source_root 自身是仓库根的情况，避免误取上层无关仓库的 commit。
    if not (source_root / ".git").exists():
        return "unknown"
    result = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def write_version(source_root: Path, project_dir: Path, source_url: str = DEFAULT_SOURCE) -> Path:
    """读取 plugin.json 的 version，写入 data-tools/VERSION，返回该文件路径。"""
    plugin = json.loads(
        (source_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    data = {
        "version": plugin["version"],
        "source_commit": _source_commit(source_root),
        "synced_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source_url,
    }
    dest = project_dir / "data-tools" / "VERSION"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest


def render_targets(
    source_root: Path, project_dir: Path, targets: list[str]
) -> list[Path]:
    """在 project_dir 下渲染各工具入口（保留 <TOOLS_DIR> 占位符），返回生成文件列表。"""
    return install(
        targets,
        "project",
        project_dir,
        source_root,
        home=project_dir,
        portable=True,
    )


def upsert_gitignore(project_dir: Path, names: list[str] | None = None) -> Path:
    """在 project_dir/.gitignore 写入或刷新 data-tools 标记块，返回该文件路径。"""
    project_dir = Path(project_dir)
    if names is None:
        tools = project_dir / "data-tools"
        names = skill_names(tools) if tools.is_dir() else []
    path = project_dir / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = re.sub(
        rf"{re.escape(GITIGNORE_BEGIN)}.*?{re.escape(GITIGNORE_END)}\n?",
        "",
        existing,
        flags=re.S,
    )
    prefix = existing.rstrip() + "\n\n" if existing.strip() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((prefix + gitignore_block(names)).rstrip() + "\n", encoding="utf-8")
    return path


def _require_project_id(project_id: str) -> str:
    """校验项目 ID 可安全用作单层目录名；拒绝路径分隔符、盘符和 `..`。"""
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("项目 ID 不能为空")
    if (
        "/" in project_id
        or "\\" in project_id
        or ":" in project_id
        or ".." in project_id
        or PureWindowsPath(project_id).drive
    ):
        raise ValueError(
            f"项目 ID 非法：{project_id!r}（不能包含 /、\\、:、.. 或盘符前缀）"
        )
    return project_id


def _default_project_yaml(project_id: str) -> str:
    """把 default_project 安全地写成 YAML 行，特殊字符会自动加引号。"""
    return yaml.safe_dump({"default_project": project_id}, allow_unicode=True).strip()


def init_data_dirs(project_dir: Path, project_id: str | None) -> list[Path]:
    """创建项目数据目录，补齐 config.yaml / .env.example，绝不覆盖已有数据文件。"""
    project_dir = Path(project_dir)
    data_root = project_dir / ".data-tools"
    created: list[Path] = []
    if not data_root.exists():
        created.append(data_root)
    data_root.mkdir(parents=True, exist_ok=True)

    if not project_id:
        return created

    project_id = _require_project_id(project_id)
    project_path = data_root / "projects" / project_id
    if not project_path.exists():
        created.append(project_path)
    project_path.mkdir(parents=True, exist_ok=True)

    config = data_root / "config.yaml"
    if not config.exists():
        config.write_text(_default_project_yaml(project_id) + "\n", encoding="utf-8")
        created.append(config)
    else:
        text = config.read_text(encoding="utf-8")
        if not re.search(r"^default_project\s*:", text, flags=re.M):
            separator = "" if (not text or text.endswith("\n")) else "\n"
            config.write_text(
                text + separator + _default_project_yaml(project_id) + "\n",
                encoding="utf-8",
            )
            created.append(config)

    env_example = project_path / ".env.example"
    if not env_example.exists():
        env_example.write_text(ENV_EXAMPLE_TEMPLATE, encoding="utf-8")
        created.append(env_example)

    return created


def render_project_readme(
    source_root: Path, project_dir: Path, project_id: str | None
) -> Path:
    """用模板渲染 data-tools/README.md（替换项目 ID），返回该文件路径。"""
    template = (Path(source_root) / "skills" / "_TEMPLATE" / "project-readme.md").read_text(
        encoding="utf-8"
    )
    dest = Path(project_dir) / "data-tools" / "README.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(template.replace("<PROJECT_ID>", project_id or "<项目ID>"), encoding="utf-8")
    return dest


def _planned_target_paths(
    source_root: Path, project_dir: Path, targets: tuple[str, ...]
) -> list[Path]:
    """dry-run 用：按 install 的布局推算将生成的入口文件路径，不写文件。"""
    names = skill_names(source_root)
    paths: list[Path] = []
    for tool in targets:
        if tool in ("claude", "dsh"):
            paths.extend(
                project_dir / f".{tool}" / "skills" / name / "SKILL.md" for name in names
            )
        elif tool == "cursor":
            paths.extend(project_dir / ".cursor" / "rules" / f"{name}.mdc" for name in names)
        else:
            raise ValueError(f"未知工具 {tool}")
    return paths


def sync_project(
    project_dir: Path,
    project_id: str | None = None,
    targets: tuple[str, ...] = ("claude",),
    source_root: Path | None = None,
    source_url: str = DEFAULT_SOURCE,
    dry_run: bool = False,
) -> SyncResult:
    """把工具包同步进业务仓库；dry_run 只打印计划路径，不写任何文件。"""
    project_dir = Path(project_dir)
    source = (
        Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    )
    targets = tuple(targets)

    if project_id:
        project_id = _require_project_id(project_id)

    if not project_dir.is_dir():
        raise FileNotFoundError(f"项目目录不存在：{project_dir}")

    missing = [item for item in CORE_ITEMS if not (source / item).exists()]
    if missing:
        raise FileNotFoundError(f"工具包缺少核心条目：{', '.join(missing)}（源：{source}）")

    # 先校验 targets 再动文件，避免非法工具名导致半同步。
    _validate_targets(targets)
    planned_targets = _planned_target_paths(source, project_dir, targets)

    result = SyncResult()

    if dry_run:
        result.copied = [
            project_dir / "data-tools" / item
            for item in TOOLKIT_ITEMS
            if (source / item).exists()
        ]
        result.rendered = [
            project_dir / "data-tools" / "VERSION",
            *planned_targets,
            project_dir / "data-tools" / "README.md",
            project_dir / ".gitignore",
        ]
        if project_id:
            data_root = project_dir / ".data-tools"
            result.rendered.extend(
                [
                    data_root / "config.yaml",
                    data_root / "projects" / project_id / ".env.example",
                ]
            )
        for path in (*result.copied, *result.rendered):
            print(path)
        return result

    result.copied = copy_toolkit(source, project_dir)
    result.removed = remove_obsolete_toolkit_files(project_dir)
    result.rendered.append(write_version(source, project_dir, source_url))
    result.rendered.extend(render_targets(source, project_dir, list(targets)))

    if project_id:
        project_path = project_dir / ".data-tools" / "projects" / project_id
        result.preserved.extend(
            project_path / name for name in PROJECT_DATA_FILES if (project_path / name).exists()
        )

    result.rendered.extend(init_data_dirs(project_dir, project_id))
    result.rendered.append(render_project_readme(source, project_dir, project_id))
    names = skill_names(source)
    result.rendered.append(upsert_gitignore(project_dir, names))
    agents = remove_agents_block(project_dir)
    if agents is not None:
        result.cleaned.append(agents)
        print(
            f"[data-tools] 已从 {agents.name} 移除 data-tools 块；"
            "如该文件已被 git 跟踪，请提交这次删除。",
            file=sys.stderr,
        )
    warn_if_tracked(project_dir, names)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 data-tools 同步进业务仓库")
    parser.add_argument("--project-dir", type=Path, required=True, help="业务仓库根目录")
    parser.add_argument("--project-id", help="写入 .data-tools/config.yaml 的 default_project")
    parser.add_argument("--targets", default="claude", help="逗号分隔：claude,cursor,dsh")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-url", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的动作，不写文件")
    args = parser.parse_args(argv)

    targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
    if not (args.project_dir / ".git").exists():
        print(f"警告：{args.project_dir} 不是 git 仓库，继续同步", file=sys.stderr)

    try:
        result = sync_project(
            args.project_dir,
            args.project_id,
            targets,
            args.source,
            args.source_url,
            args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    if not args.dry_run:
        for path in (
            *result.copied,
            *result.rendered,
            *result.preserved,
            *result.removed,
            *result.cleaned,
        ):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
