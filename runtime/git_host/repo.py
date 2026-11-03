"""本地 git 操作封装。所有规则判断先于 git 写操作，失败时不改动仓库。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .rules import RuleViolation, check_commit_message, check_commit_paths, check_merge, check_sync

PROTECTED_BRANCHES = ("test", "dev", "prod")
PUSH_FORBIDDEN_LOCAL = ("test", "prod")  # dev 允许直接推送，其余只能走 MR


class RepoError(Exception):
    pass


@dataclass
class Commit:
    hash: str
    subject: str
    files: int = 0


@dataclass
class FlowReport:
    prod_into_test: list[Commit] = field(default_factory=list)
    test_net_vs_test: list[Commit] = field(default_factory=list)
    test_net_vs_target: list[Commit] = field(default_factory=list)
    prod_only: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.prod_only


class Repo:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RepoError(detail[-1] if detail else f"git {args[0]} 失败")
        return result.stdout.strip()

    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def is_clean(self) -> bool:
        return self._git("status", "--porcelain") == ""

    def staged_paths(self) -> list[str]:
        out = self._git("diff", "--cached", "--name-only")
        return [line for line in out.splitlines() if line.strip()]

    def commit(self, message: str, forbidden: list[str]) -> str:
        check_commit_message(message)
        check_commit_paths(self.staged_paths(), forbidden)
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "--short", "HEAD")

    def _rev_list(self, spec: str) -> list[str]:
        out = self._git("rev-list", "--cherry-pick", "--right-only", spec, check=False)
        return [line for line in out.splitlines() if line.strip()]

    def _ref(self, branch: str) -> str | None:
        for candidate in (f"origin/{branch}", branch):
            if self._git("rev-parse", "--verify", "-q", candidate, check=False):
                return candidate
        return None

    def fork_base(self, source: str) -> str | None:
        best: tuple[int, str] | None = None
        for base in PROTECTED_BRANCHES:
            if base == source:
                continue
            ref = self._ref(base)
            if ref is None:
                continue
            count = self._git("rev-list", "--count", f"{ref}..{source}", check=False)
            if not count.isdigit():
                continue
            if best is None or int(count) < best[0]:
                best = (int(count), base)
        return best[1] if best else None

    def bring_in_commits(self, source: str, target: str, base: str) -> list[str]:
        ordered = self._rev_list(f"{target}...{source}")
        own = set(self._rev_list(f"{base}...{source}"))
        return [h for h in ordered if h not in own]

    def require_clean(self) -> None:
        """已跟踪文件有未提交改动、或存在未完成的合并时拒绝继续；未跟踪文件不算。"""
        if self._git("status", "--porcelain", "--untracked-files=no"):
            raise RepoError("工作区有未提交的改动或未完成的合并，请先提交/暂存或处理完再继续")

    def fetch(self) -> None:
        if "origin" in self._git("remote", check=False).split():
            self._git("fetch", "-q", "origin")

    def _has_ref(self, ref: str) -> bool:
        return bool(self._git("rev-parse", "--verify", "-q", ref, check=False))

    def _merge_keep_scene(self, *merge_args: str) -> None:
        """合并；冲突时保留现场（不 abort），报告冲突文件与后续操作。"""
        result = subprocess.run(
            ["git", "-C", str(self.path), "merge", "-q", *merge_args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return
        conflicts = self._git("diff", "--name-only", "--diff-filter=U", check=False)
        files = ", ".join(line for line in conflicts.splitlines() if line.strip())
        if not files:
            self._git("merge", "--abort", check=False)
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RepoError(detail[-1] if detail else "合并失败")
        raise RepoError(
            f"合并冲突，现场已保留在 {self.current_branch()} 上。冲突文件：{files}。"
            "解决后执行 git add <文件> 与 git commit --no-edit；放弃则执行 git merge --abort"
        )

    def merge(
        self,
        source: str,
        target: str,
        source_base: str | None,
        forbidden_targets: list[str],
        confirm_bring_in: bool = False,
    ) -> None:
        if target in forbidden_targets:
            check_merge(source, target, source_base, [])
        self.require_clean()
        self.fetch()
        target_ref = f"origin/{target}" if self._has_ref(f"origin/{target}") else target
        base = source_base or self.fork_base(source) or target
        base_ref = self._ref(base) or base
        bring_in = self.bring_in_commits(source, target_ref, base_ref) if target == "dev" else []
        pending = check_merge(source, target, source_base, bring_in)
        if pending and not confirm_bring_in:
            raise RuleViolation(
                "net-increment",
                f"将带入 {target} 的非本分支内容 {len(pending)} 个提交，确认后请加 --confirm-bring-in",
            )
        self._git("checkout", "-q", target)
        if target_ref != target:
            ff = subprocess.run(
                ["git", "-C", str(self.path), "merge", "--ff-only", "-q", target_ref],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if ff.returncode != 0:
                raise RepoError(
                    f"本地 {target} 与 {target_ref} 已分叉（本地有未推送的提交），"
                    "请先处理本地 dev 再合并，工具不会强行覆盖"
                )
        self._merge_keep_scene("--no-ff", source)

    def sync(self, source: str | None = None) -> int:
        """把当前功能分支的目标分支（origin/<目标>）最新内容合进来，返回带入的提交数。"""
        branch = self.current_branch()
        target = check_sync(branch, source)
        self.require_clean()
        self.fetch()
        ref = f"origin/{target}"
        if not self._has_ref(ref):
            raise RepoError(f"找不到 {ref}，无法同步")
        behind = int(self._git("rev-list", "--count", f"HEAD..{ref}"))
        if behind:
            self._merge_keep_scene("--no-edit", ref)
        return behind

    def push(self, branch: str) -> None:
        if branch in PUSH_FORBIDDEN_LOCAL:
            raise RuleViolation(
                "push-target",
                f"本地分支名为 {branch} 时不允许推送：test、prod 只能经 MR 进入，"
                "请使用 feature/<目标>/<用户标识>/<任务号>-<描述>",
            )
        self._git("push", "-u", "origin", f"{branch}:{branch}")

    def create_branch(self, name: str, target: str) -> None:
        self._git("fetch", "-q", "origin")
        self._git("checkout", "-q", "-b", name, "--no-track", f"origin/{target}")
        ahead = self._git("rev-list", "--count", f"origin/{target}..HEAD")
        if ahead != "0":
            raise RepoError(f"新分支起点与 origin/{target} 不一致（领先 {ahead} 个提交）")

    def hotfix_commits(self, fix_branch: str, prod_ref: str = "origin/prod") -> list[str]:
        commits = self._rev_list(f"{prod_ref}...{fix_branch}")
        commits = list(reversed(commits))
        if not commits:
            raise RepoError("热修复分支相对 prod 无新提交")
        return commits

    def cherry_pick(self, commits: list[str]) -> list[str]:
        created: list[str] = []
        for commit in commits:
            result = subprocess.run(
                ["git", "-C", str(self.path), "cherry-pick", "-x", commit],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                conflicts = self._git("diff", "--name-only", "--diff-filter=U", check=False)
                self._git("cherry-pick", "--abort", check=False)
                files = ", ".join(line for line in conflicts.splitlines() if line.strip()) or "未知文件"
                raise RepoError(f"cherry-pick 冲突，已中止。冲突文件：{files}")
            created.append(self._git("rev-parse", "--short", "HEAD"))
        return created

    def check_prod_derived(self, source_base: str | None, target_branch: str) -> None:
        if source_base == "prod" and target_branch in ("dev", "test"):
            raise RuleViolation(
                "prod-derived",
                f"prod 衍生分支不能直接合并到 {target_branch}，请先经过 test 衍生的同步分支",
            )

    def verify_flow(self, prod_branch: str, test_branch: str, target: str) -> FlowReport:
        report = FlowReport()
        report.prod_into_test = self._commits(f"origin/{test_branch}...{prod_branch}")
        report.test_net_vs_test = self._commits(f"origin/{test_branch}...{test_branch}")
        report.test_net_vs_target = self._commits(f"origin/{target}...{test_branch}")
        prod_only = self._rev_list(f"origin/{test_branch}...origin/{prod_branch}")
        report.prod_only = prod_only
        return report

    def _commits(self, spec: str) -> list[Commit]:
        hashes = self._rev_list(spec)
        out: list[Commit] = []
        for h in hashes:
            subject = self._git("log", "-1", "--format=%s", h, check=False)
            files = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", h, check=False)
            out.append(Commit(hash=h, subject=subject, files=len([f for f in files.splitlines() if f.strip()])))
        return out
