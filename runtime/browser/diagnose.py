"""浏览器失败诊断包。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import FlowDef
from .flow import FlowResult
from .report import ARTIFACT_KEEP, ARTIFACT_MAX_AGE, artifacts_dir, prune, timestamp

_SENSITIVE_HEADER_PARTS = ("authorization", "cookie", "token", "secret", "api-key", "apikey", "password")
_SENSITIVE_QUERY_PARTS = ("token", "authorization", "password", "secret", "passwd", "cookie")


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if not any(part in key.lower() for part in _SENSITIVE_HEADER_PARTS)
    }


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = [
        (key, "***" if any(part in key.lower() for part in _SENSITIVE_QUERY_PARTS) else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(pairs, safe="*")))


_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"(?i)\bBearer(?:\s|%20)+[A-Za-z0-9._~+/=-]+")
_KEYED = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*(?:token|authorization|password|passwd|secret|api[-_]?key)[A-Za-z0-9_-]*)=([^&\s\"'<>]+)"
)


def scrub_text(text: str) -> str:
    text = _JWT.sub("***", text)
    text = _BEARER.sub("Bearer ***", text)
    return _KEYED.sub(lambda m: f"{m.group(1)}=***", text)


class PageCollector:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.console: list[str] = []

    def attach(self, page: Any) -> None:
        def on_response(response: Any) -> None:
            try:
                request = response.request
                self.requests.append(
                    {
                        "method": request.method,
                        "url": redact_url(response.url),
                        "status": response.status,
                        "request_headers": redact_headers(dict(request.headers)),
                    }
                )
                if len(self.requests) > 200:
                    del self.requests[:-200]
            except Exception:
                pass

        def on_console(message: Any) -> None:
            try:
                self.console.append(f"{message.type}: {message.text}")
            except Exception:
                pass

        page.on("response", on_response)
        page.on("console", on_console)


def _screenshot(page: Any, path: Path) -> None:
    page.screenshot(path=str(path), full_page=True)


def _write(path: Path, content: str) -> None:
    try:
        path.write_text(scrub_text(content), encoding="utf-8")
    except Exception:
        pass


def _display_line(problem: dict) -> str:
    kind = problem.get("kind") or "unknown"
    field = problem.get("field")
    text = problem.get("text")
    element = str(problem.get("tag") or "element")
    testid = problem.get("testid")
    css_class = problem.get("class")
    if testid:
        element += f'[data-testid="{testid}"]'
    elif css_class:
        element += "." + str(css_class).replace(" ", ".")
    if kind == "empty_value" and field and text:
        head = f"- [{kind}] 字段 {field}（期望值 {text!r}）"
    elif field:
        head = f"- [{kind}] 字段 {field}"
    elif text:
        head = f"- [{kind}] 文本 {text!r}"
    else:
        head = f"- [{kind}]"
    return f"{head} {element}：{problem.get('reason') or ''}"


def _diagnosis(page: Any, result: FlowResult) -> str:
    failure = result.failure
    try:
        url = redact_url(page.url)
    except Exception:
        url = "unknown"
    try:
        title = page.title()
    except Exception:
        title = "unknown"

    lines = [
        "# 浏览器流程失败诊断",
        "",
        f"- 流程：{result.flow}",
        f"- 环境：{result.env}",
    ]
    if failure is not None:
        lines.extend(
            [
                f"- 失败步骤：{failure.step_index}. {failure.step_name}",
                f"- 错误：{failure.message}",
                f"- 期望：{failure.expected}",
                f"- 实际：{failure.actual}",
            ]
        )
    lines.extend(
        [
            f"- 当前 URL：{url}",
            f"- 页面标题：{title}",
        ]
    )
    api_errors = (failure.detail or {}).get("api_errors") if failure is not None else None
    if api_errors:
        lines.extend(["", "## 接口异常"])
        for item in api_errors:
            lines.append(f"- {item['method']} {item['url']} → {item['reason']}")
            if item.get("body"):
                lines.append(f"  - 响应：{item['body']}")

    display_problems = (failure.detail or {}).get("display_problems") if failure is not None else None
    if display_problems:
        lines.extend(["", "## 显示问题"])
        lines.extend(_display_line(item) for item in display_problems)

    lines.extend(["", "## 步骤"])
    for step in result.steps:
        error = f" {step.error}" if step.error else ""
        lines.append(f"- {step.name}: {step.status} ({step.duration_ms}ms){error}")

    lines.extend(["", "## 建议"])
    if api_errors:
        lines.append("- 接口已经报错：优先排查后端或入参，而不是选择器；确属预期时在步骤上加 allow_api_error。")
    if display_problems:
        lines.append("- 显示问题：优先核对该字段是否漏渲染、容器/列宽是否不足；设计上允许省略的用 allow_truncate 放行。")
    lines.extend(
        [
            "- 检查选择器是否变化，优先用 data-testid 或行内范围限定。",
            "- 检查等待信号是否对应实际接口或 URL 变化。",
            "- 检查页面是否跳转、是否有前置条件未满足。",
            "",
        ]
    )
    return "\n".join(lines)


def capture(
    page: Any,
    project_id: str,
    flow: FlowDef,
    result: FlowResult,
    collector: PageCollector,
    *,
    trace_path: Path | None = None,
) -> Path:
    directory = artifacts_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{flow.name}-{timestamp()}"
    out = directory / stem
    index = 2
    while out.exists():
        out = directory / f"{stem}-{index}"
        index += 1
    out.mkdir(parents=True)

    try:
        _screenshot(page, out / "failure.png")
    except Exception:
        pass
    try:
        (out / "page.html").write_text(scrub_text(page.content()), encoding="utf-8")
    except Exception:
        pass
    _write(out / "requests.json", json.dumps(collector.requests, ensure_ascii=False, indent=2))
    _write(out / "console.log", "\n".join(collector.console))
    try:
        (out / "flow.snapshot.yaml").write_text(flow.path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    run_lines = [
        f"{step.name}\t{step.status}\t{step.duration_ms}ms" + (f"\t{step.error}" if step.error else "")
        for step in result.steps
    ]
    _write(out / "run.log", "\n".join(run_lines))
    _write(out / "diagnosis.md", _diagnosis(page, result))

    if trace_path is not None and Path(trace_path).exists():
        try:
            shutil.copyfile(trace_path, out / "trace.zip")
        except Exception:
            pass

    prune(directory, ARTIFACT_KEEP, ARTIFACT_MAX_AGE)
    return out
