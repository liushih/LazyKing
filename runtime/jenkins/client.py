"""Jenkins HTTP 客户端：Basic 认证、错误分类、输出脱敏。"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests

FOLDER_MARK = "Folder"
_AUTH_HEADER = re.compile(r"(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]{8,}")


class JenkinsError(Exception):
    """kind：auth / permission / notfound / network / http / param / queue / timeout。"""

    def __init__(self, message: str, kind: str, job: str | None = None, url: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.job = job
        self.url = url


@dataclass
class JobParam:
    name: str
    type: str
    default: str | None
    choices: list[str] = field(default_factory=list)

    @property
    def required(self) -> bool:
        return self.default is None


@dataclass
class BuildStatus:
    number: int
    building: bool
    result: str | None
    url: str


@dataclass
class InFlightBuild:
    """Jenkins 队列项或正在运行的构建；params 是触发参数，无参数任务为空字典。"""

    kind: str  # "queue" | "build"
    job: str
    params: dict[str, str]
    number: int | None = None
    item_id: int | None = None
    queue_id: int | None = None


def _parse_params(text: object) -> dict[str, str]:
    if isinstance(text, dict):
        return {str(k): str(v) for k, v in text.items()}
    params: dict[str, str] = {}
    for line in str(text or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            params[key.strip()] = value.strip()
    return params


def _build_params(raw: dict) -> dict[str, str]:
    for action in raw.get("actions") or []:
        parameters = action.get("parameters")
        if parameters:
            return {str(p["name"]): str(p.get("value", "")) for p in parameters}
    return {}


class JenkinsClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        token: str,
        session=None,
        timeout: float = 15.0,
        retries: int = 2,
        retry_delay: float = 0.5,
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.sleep = sleep
        self._crumb: dict[str, str] | None = None

    # ---- 内部 ----

    def _redact(self, text: str) -> str:
        if self.token:
            text = text.replace(self.token, "***")
            pair = base64.b64encode(f"{self.user}:{self.token}".encode()).decode()
            text = text.replace(pair, "***")
        return _AUTH_HEADER.sub(lambda m: f"{m.group(1)} ***", text)

    @staticmethod
    def job_path(job: str) -> str:
        return "".join(f"/job/{part}" for part in job.split("/") if part)

    def _send(self, method: str, path: str, job: str | None, attempts: int, kwargs: dict):
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                return self.session.request(
                    method, url, auth=(self.user, self.token), timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                last = exc
                if attempt + 1 < attempts:
                    self.sleep(self.retry_delay)
        raise JenkinsError(
            self._redact(f"{method} {path} 连接失败：{type(last).__name__}"), "network", job, url
        ) from None

    def _crumb_headers(self) -> dict[str, str]:
        if self._crumb is None:
            try:
                data = self._request("GET", "/crumbIssuer/api/json").json()
                self._crumb = {str(data["crumbRequestField"]): str(data["crumb"])}
            except (JenkinsError, KeyError, ValueError):
                self._crumb = {}
        return self._crumb

    def _request(self, method: str, path: str, *, job: str | None = None, retry: bool = True, **kwargs):
        """读请求可重试网络错误；写请求只发一次，仅在 crumb 被拒时带 crumb 重发一次。"""
        attempts = self.retries + 1 if retry else 1
        if method != "GET" and self._crumb:
            kwargs["headers"] = {**kwargs.get("headers", {}), **self._crumb}
        resp = self._send(method, path, job, attempts, kwargs)
        if method != "GET" and resp.status_code == 403 and "crumb" in (resp.text or "").lower():
            crumb = self._crumb_headers()
            if crumb:
                kwargs["headers"] = {**kwargs.get("headers", {}), **crumb}
                resp = self._send(method, path, job, 1, kwargs)
        self._raise_for_status(resp, method, path, job, f"{self.base_url}{path}")
        return resp

    def _raise_for_status(self, resp, method: str, path: str, job: str | None, url: str) -> None:
        status = resp.status_code
        if status < 400:
            return
        if status == 401:
            raise JenkinsError("账号或 token 无效", "auth", job, url)
        if status == 403:
            target = f"任务 {job}" if job else path
            raise JenkinsError(f"当前账号无权访问 {target}", "permission", job, url)
        if status == 404:
            target = f"任务 {job}" if job else path
            raise JenkinsError(f"{target} 不存在", "notfound", job, url)
        raise JenkinsError(f"{method} {path} 返回 HTTP {status}", "http", job, url)

    # ---- 只读接口 ----

    def whoami(self) -> str:
        data = self._request("GET", "/me/api/json").json()
        return str(data.get("id") or data.get("fullName") or self.user)

    def list_jobs(self) -> list[str]:
        names: list[str] = []

        def walk(prefix: str) -> None:
            path = f"{self.job_path(prefix)}/api/json" if prefix else "/api/json"
            data = self._request(
                "GET", path, job=prefix or None, params={"tree": "jobs[name,_class]"}
            ).json()
            for item in data.get("jobs") or []:
                full = f"{prefix}/{item['name']}" if prefix else item["name"]
                if FOLDER_MARK in str(item.get("_class", "")):
                    walk(full)
                else:
                    names.append(full)

        walk("")
        return sorted(names)

    def job_params(self, job: str) -> list[JobParam]:
        tree = "property[parameterDefinitions[name,type,defaultParameterValue[value],choices]]"
        data = self._request(
            "GET", f"{self.job_path(job)}/api/json", job=job, params={"tree": tree}
        ).json()
        params: list[JobParam] = []
        for prop in data.get("property") or []:
            for definition in prop.get("parameterDefinitions") or []:
                default = definition.get("defaultParameterValue")
                params.append(
                    JobParam(
                        name=str(definition["name"]),
                        type=str(definition.get("type") or ""),
                        default=None if default is None else str(default.get("value")),
                        choices=[str(c) for c in (definition.get("choices") or [])],
                    )
                )
        return params

    def build_status(self, job: str, number: int) -> BuildStatus:
        data = self._request(
            "GET",
            f"{self.job_path(job)}/{number}/api/json",
            job=job,
            params={"tree": "number,building,result,url"},
        ).json()
        return BuildStatus(
            number=int(data.get("number", number)),
            building=bool(data.get("building")),
            result=data.get("result"),
            url=str(data.get("url") or ""),
        )

    def console_tail(self, job: str, number: int, lines: int = 50) -> str:
        text = self._request("GET", f"{self.job_path(job)}/{number}/consoleText", job=job).text
        return self._redact("\n".join(text.splitlines()[-lines:]))

    # ---- 触发与等待 ----

    @staticmethod
    def _job_from_url(url: str) -> str | None:
        parts = [part for part in urlsplit(url).path.split("/") if part]
        names = [parts[i + 1] for i in range(0, len(parts) - 1, 2) if parts[i] == "job"]
        return "/".join(names) or None

    def queue_items(self) -> list[InFlightBuild]:
        data = self._request(
            "GET", "/queue/api/json", params={"tree": "items[id,params,task[name,url]]"}
        ).json()
        items: list[InFlightBuild] = []
        for raw in data.get("items") or []:
            job = self._job_from_url(str((raw.get("task") or {}).get("url") or ""))
            if job is None:
                continue
            item_id = int(raw["id"])
            items.append(
                InFlightBuild(
                    "queue", job, _parse_params(raw.get("params")), item_id=item_id, queue_id=item_id
                )
            )
        return items

    def in_flight(self, job: str) -> list[InFlightBuild]:
        """该任务排队中的项和正在运行的构建。"""
        active = [item for item in self.queue_items() if item.job == job]
        tree = "builds[number,building,queueId,actions[parameters[name,value]]]"
        data = self._request(
            "GET", f"{self.job_path(job)}/api/json", job=job, params={"tree": tree}
        ).json()
        for raw in data.get("builds") or []:
            if not raw.get("building"):
                continue
            queue_id = raw.get("queueId")
            active.append(
                InFlightBuild(
                    "build",
                    job,
                    _build_params(raw),
                    number=int(raw["number"]),
                    queue_id=None if queue_id is None else int(queue_id),
                )
            )
        return active

    def cancel_queue_item(self, item_id: int) -> None:
        self._request("POST", "/queue/cancelItem", retry=False, params={"id": item_id})

    def stop_build(self, job: str, number: int) -> None:
        self._request("POST", f"{self.job_path(job)}/{number}/stop", job=job, retry=False)

    def trigger(self, job: str, params: dict[str, str] | None) -> str:
        """params 为 None 走 /build（无参数任务）；否则走 /buildWithParameters。返回队列项地址。"""
        base = self.job_path(job)
        if params is None:
            resp = self._request("POST", f"{base}/build", job=job, retry=False)
        else:
            resp = self._request(
                "POST", f"{base}/buildWithParameters", job=job, retry=False, data=params
            )
        location = resp.headers.get("Location")
        if not location:
            raise JenkinsError(f"触发 {job} 后未返回队列地址", "queue", job)
        return location

    def wait_for_build(self, queue_url: str, timeout_s: float, poll_s: float = 2.0) -> int:
        path = urlsplit(queue_url).path.rstrip("/") + "/api/json"
        start = time.monotonic()
        while True:
            data = self._request("GET", path).json()
            if data.get("cancelled"):
                raise JenkinsError("构建在排队时被取消", "queue", url=queue_url)
            executable = data.get("executable")
            if executable:
                return int(executable["number"])
            if time.monotonic() - start >= timeout_s:
                raise JenkinsError("等待构建开始超时", "timeout", url=queue_url)
            self.sleep(poll_s)

    def wait_finished(self, job: str, number: int, timeout_s: float, poll_s: float = 5.0) -> BuildStatus:
        start = time.monotonic()
        while True:
            status = self.build_status(job, number)
            if not status.building:
                return status
            if time.monotonic() - start >= timeout_s:
                raise JenkinsError(f"等待 {job} #{number} 完成超时", "timeout", job, status.url)
            self.sleep(poll_s)
