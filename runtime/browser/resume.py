"""浏览器流程断点续跑的状态文件。

只保存步骤产出的业务变量，不保存日志里的密钥；流程文件、输入或环境变化后断点自动失效。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_SECRET_HINTS = ("password", "passwd", "secret", "token", "credential")
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def flow_fingerprint(path: Path) -> str:
    try:
        return _fingerprint(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return ""


def seed_fingerprint(values: dict[str, str]) -> str:
    payload = json.dumps(sorted(values.items()), ensure_ascii=False)
    return _fingerprint(payload)


def state_path(home: Path, project: str, env: str, flow: str) -> Path:
    name = _UNSAFE.sub("_", f"{env}-{flow}")
    return Path(home) / "browser" / "state" / project / f"{name}.json"


def _is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def save_state(
    path: Path,
    *,
    flow_hash: str,
    seed_hash: str,
    env: str,
    completed: int,
    produced: dict[str, str],
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "flow_hash": flow_hash,
        "seed_hash": seed_hash,
        "env": env,
        "completed": int(completed),
        "produced": {
            str(key): str(value)
            for key, value in produced.items()
            if not _is_secret(str(key))
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(
    path: Path,
    *,
    flow_hash: str,
    seed_hash: str,
    env: str,
    step_count: int,
) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    if (
        data.get("flow_hash") != flow_hash
        or data.get("seed_hash") != seed_hash
        or data.get("env") != env
    ):
        return None
    completed = data.get("completed")
    if not isinstance(completed, int) or completed <= 0 or completed >= step_count:
        return None
    produced = data.get("produced")
    if not isinstance(produced, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in produced.items()
    ):
        return None
    return {"completed": completed, "produced": dict(produced)}


def clear_state(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass
