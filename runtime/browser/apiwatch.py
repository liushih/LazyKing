"""页面接口异常监听：步骤等待期间接口出错时提前判定失败，不必等到超时。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

_FAIL_TYPES = {"xhr", "fetch", "document"}
_REQUEST_FAIL_TYPES = {"xhr", "fetch"}
_BODY_LIMIT = 1_000_000
_SNIPPET = 300
_DEFAULT_SUCCESS_CODES = ("0", "200", "ok", "success")


@dataclass(frozen=True)
class ApiWatchConfig:
    enabled: bool = True
    ignore: tuple[str, ...] = ()
    success_codes: tuple[str, ...] = _DEFAULT_SUCCESS_CODES
    # 接口报错后给页面自行恢复（重试成功）的宽限期；宽限期内等待条件满足就不判失败。
    grace_ms: int = 1500


@dataclass
class ApiError:
    method: str
    url: str
    status: int
    reason: str
    at: float
    response: Any = field(default=None, repr=False)
    body: str = ""


class ApiFailure(Exception):
    def __init__(self, errors: list[ApiError]):
        from .diagnose import redact_url, scrub_text

        for error in errors:
            if not error.body and error.response is not None:
                error.body = _read_text(error.response)
        first = errors[0]
        self.expected = "接口正常"
        self.actual = first.reason
        self.detail = {
            "api_errors": [
                {
                    "method": item.method,
                    "url": redact_url(item.url),
                    "status": item.status,
                    "reason": item.reason,
                    "body": scrub_text(item.body[:_SNIPPET]),
                }
                for item in errors
            ]
        }
        head = self.detail["api_errors"][0]
        message = f"接口异常：{head['method']} {head['url']} → {head['reason']}"
        if head["body"]:
            message += f"；响应：{head['body']}"
        if len(errors) > 1:
            message += f"（另有 {len(errors) - 1} 个接口异常）"
        super().__init__(message)


def judge_status(status: int, resource_type: str, cfg: ApiWatchConfig) -> str | None:
    """HTTP 层：只看接口（xhr/fetch）与主页面请求，图片/脚本等静态资源 404 不算。"""
    if resource_type in _FAIL_TYPES and status >= 400:
        return f"HTTP {status}"
    return None


def judge_body(text: str, cfg: ApiWatchConfig) -> str | None:
    """业务层：HTTP 200 但响应体顶层 success=false 或 code 不在成功码内。"""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    message = next((str(data[key]) for key in ("msg", "message", "error") if data.get(key)), "")
    suffix = f" msg={message}" if message else ""
    if data.get("success") is True:
        return None
    if data.get("success") is False:
        return f"业务失败 success=false{suffix}"
    code = data.get("code")
    if code is None or isinstance(code, (bool, dict, list)):
        return None
    if str(code).strip().lower() not in cfg.success_codes:
        return f"业务码 code={code}{suffix}"
    return None


def is_ignored(url: str, cfg: ApiWatchConfig) -> bool:
    return any(part in url for part in cfg.ignore)


def _read_text(response: Any) -> str:
    try:
        return response.text()
    except Exception:
        return ""


def _body_error(response: Any, cfg: ApiWatchConfig) -> str | None:
    headers = response.headers
    if "json" not in (headers.get("content-type") or "").lower():
        return None
    try:
        if int(headers.get("content-length") or 0) > _BODY_LIMIT:
            return None
    except ValueError:
        pass
    text = _read_text(response)
    return judge_body(text, cfg) if text else None


class ApiWatch:
    def __init__(self, cfg: ApiWatchConfig):
        self.cfg = cfg
        self._page: Any = None
        self._errors: list[ApiError] = []
        self._pending: list[Any] = []
        self._allow: bool | list[str] = False

    @property
    def active(self) -> bool:
        return self.cfg.enabled and self._allow is not True

    def attach(self, page: Any) -> None:
        self._page = page
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)

    def detach(self) -> None:
        if self._page is None:
            return
        for event, handler in (("response", self._on_response), ("requestfailed", self._on_request_failed)):
            try:
                self._page.remove_listener(event, handler)
            except Exception:
                pass

    def begin_step(self, allow: bool | list[str] = False) -> None:
        self._errors = []
        self._pending = []
        self._allow = allow

    def check(self) -> None:
        """等待循环里反复调用：有接口异常且已过宽限期（页面仍没恢复）就判失败。"""
        if not self.active:
            return
        self._drain()
        now = time.monotonic()
        due = [error for error in self._errors if (now - error.at) * 1000 >= self.cfg.grace_ms]
        if due:
            raise ApiFailure(due)

    def verify(self, response: Any) -> None:
        """显式等待（wait_response）拿到的响应：状态或业务码异常立即判失败，不给宽限期。"""
        if not self.active:
            return
        request = response.request
        url = response.url
        if is_ignored(url, self.cfg) or self._allowed(url):
            return
        reason = judge_status(response.status, request.resource_type, self.cfg) or _body_error(response, self.cfg)
        if reason:
            raise ApiFailure([self._error(request.method, url, response.status, reason, response)])

    def _allowed(self, url: str) -> bool:
        return isinstance(self._allow, list) and any(part in url for part in self._allow)

    def _error(self, method: str, url: str, status: int, reason: str, response: Any = None) -> ApiError:
        return ApiError(method, url, status, reason, time.monotonic(), response)

    def _on_response(self, response: Any) -> None:
        try:
            if not self.active:
                return
            request = response.request
            resource_type = request.resource_type
            if resource_type not in _FAIL_TYPES:
                return
            if resource_type == "document" and request.frame != self._page.main_frame:
                return
            url = response.url
            if is_ignored(url, self.cfg) or self._allowed(url):
                return
            reason = judge_status(response.status, resource_type, self.cfg)
            if reason:
                self._errors.append(self._error(request.method, url, response.status, reason, response))
            elif resource_type != "document":
                self._pending.append(response)
        except Exception:
            pass

    def _on_request_failed(self, request: Any) -> None:
        try:
            if not self.active or request.resource_type not in _REQUEST_FAIL_TYPES:
                return
            failure = request.failure
            # 页面跳转或前端主动取消的请求会报 ERR_ABORTED，不是接口故障。
            if not failure or "ERR_ABORTED" in failure:
                return
            if is_ignored(request.url, self.cfg) or self._allowed(request.url):
                return
            self._errors.append(self._error(request.method, request.url, 0, f"请求失败 {failure}"))
        except Exception:
            pass

    def _drain(self) -> None:
        pending, self._pending = self._pending, []
        for response in pending:
            try:
                reason = _body_error(response, self.cfg)
                if reason:
                    request = response.request
                    self._errors.append(
                        self._error(request.method, response.url, response.status, reason, response)
                    )
            except Exception:
                pass
