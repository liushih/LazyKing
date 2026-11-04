"""Jenkins HTTP 客户端：Basic 认证、错误分类、输出脱敏。"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field

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

    def _request(self, method: str, path: str, *, job: str | None = None, retry: bool = True, **kwargs):
        url = f"{self.base_url}{path}"
        attempts = self.retries + 1 if retry else 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self.session.request(
                    method, url, auth=(self.user, self.token), timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                last = exc
                if attempt + 1 < attempts:
                    self.sleep(self.retry_delay)
                continue
            self._raise_for_status(resp, method, path, job, url)
            return resp
        raise JenkinsError(
            self._redact(f"{method} {path} 连接失败：{type(last).__name__}"), "network", job, url
        ) from None

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
