import base64

import pytest
import requests

from runtime.jenkins.client import JenkinsClient, JenkinsError, JobParam

FAKE = "fake-jenkins-token-123"  # noqa: secrets
BASE = "http://jenkins.example.com"


class _Resp:
    def __init__(self, status=200, body=None, text="", headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._body


class _Sess:
    """按 URL 子串路由；同一路由可给响应列表（依次消耗，最后一个重复使用）。"""

    def __init__(self, routes=None, default=None):
        self.routes = {k: (list(v) if isinstance(v, list) else [v]) for k, v in (routes or {}).items()}
        self.default = default
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for key in sorted(self.routes, key=len, reverse=True):
            if key in url:
                queue = self.routes[key]
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(item, Exception):
                    raise item
                return item
        if self.default is not None:
            return self.default
        raise AssertionError(f"未预期的请求 {method} {url}")


def _client(sess, **kw):
    return JenkinsClient(BASE + "/", "u", FAKE, session=sess, retry_delay=0, **kw)


def test_uses_basic_auth_and_trims_base_url():
    sess = _Sess(default=_Resp(body={"id": "u"}))
    _client(sess).whoami()
    method, url, kwargs = sess.calls[0]
    assert "//api" not in url and "//me" not in url
    assert url.startswith(BASE + "/")
    assert kwargs["auth"] == ("u", FAKE)


def test_job_path_nests_folders():
    sess = _Sess(default=_Resp(body={"number": 3, "building": False, "result": "SUCCESS", "url": "x"}))
    client = _client(sess)
    assert client.job_path("a/b") == "/job/a/job/b"
    client.build_status("a/b", 3)
    assert sess.calls[0][1] == f"{BASE}/job/a/job/b/3/api/json"


def test_list_jobs_recurses_into_folders():
    folder = "com.cloudbees.hudson.plugins.folder.Folder"
    sess = _Sess(routes={
        f"{BASE}/api/json": _Resp(body={"jobs": [
            {"name": "top", "_class": "hudson.model.FreeStyleProject"},
            {"name": "dir", "_class": folder},
        ]}),
        f"{BASE}/job/dir/api/json": _Resp(body={"jobs": [
            {"name": "inner", "_class": "hudson.model.FreeStyleProject"},
        ]}),
    })
    assert _client(sess).list_jobs() == ["dir/inner", "top"]


def test_job_params_parses_definitions():
    sess = _Sess(default=_Resp(body={"property": [{"parameterDefinitions": [
        {"name": "BRANCH", "type": "StringParameterDefinition", "defaultParameterValue": {"value": "main"}},
        {"name": "ENV", "type": "ChoiceParameterDefinition", "defaultParameterValue": {"value": "dev"},
         "choices": ["dev", "test"]},
        {"name": "TICKET", "type": "StringParameterDefinition", "defaultParameterValue": None},
    ]}]}))
    params = _client(sess).job_params("job1")
    assert params == [
        JobParam("BRANCH", "StringParameterDefinition", "main", []),
        JobParam("ENV", "ChoiceParameterDefinition", "dev", ["dev", "test"]),
        JobParam("TICKET", "StringParameterDefinition", None, []),
    ]
    assert [p.required for p in params] == [False, False, True]


def test_job_without_params_returns_empty_list():
    sess = _Sess(default=_Resp(body={"property": [{}, {"_class": "other"}]}))
    assert _client(sess).job_params("job1") == []


def test_build_status_building_and_finished():
    sess = _Sess(routes={
        "/1/api/json": _Resp(body={"number": 1, "building": True, "result": None, "url": "http://j/1/"}),
        "/2/api/json": _Resp(body={"number": 2, "building": False, "result": "SUCCESS", "url": "http://j/2/"}),
    })
    client = _client(sess)
    running = client.build_status("job1", 1)
    done = client.build_status("job1", 2)
    assert (running.building, running.result) == (True, None)
    assert (done.building, done.result, done.url) == (False, "SUCCESS", "http://j/2/")


def test_console_tail_keeps_last_lines():
    text = "\n".join(f"line {i}" for i in range(100))
    tail = _client(_Sess(default=_Resp(text=text))).console_tail("job1", 5, lines=50)
    assert tail.splitlines()[0] == "line 50"
    assert tail.splitlines()[-1] == "line 99"
    assert len(tail.splitlines()) == 50


def test_console_tail_redacts_token_and_auth_header():
    pair = base64.b64encode(f"u:{FAKE}".encode()).decode()
    text = f"token={FAKE}\nAuthorization: Basic {pair}\nBearer abcdefghijklmnop12345\nok"
    tail = _client(_Sess(default=_Resp(text=text))).console_tail("job1", 5)
    assert FAKE not in tail
    assert pair not in tail
    assert "abcdefghijklmnop12345" not in tail
    assert "***" in tail
    assert tail.splitlines()[-1] == "ok"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "permission"), (404, "notfound")])
def test_error_mapping(status, kind):
    client = _client(_Sess(default=_Resp(status)))
    with pytest.raises(JenkinsError) as exc:
        client.build_status("job1", 1)
    assert exc.value.kind == kind
    assert exc.value.job == "job1"
    if kind == "permission":
        assert "job1" in str(exc.value)


def test_server_error_is_http_kind():
    with pytest.raises(JenkinsError) as exc:
        _client(_Sess(default=_Resp(500))).build_status("job1", 1)
    assert exc.value.kind == "http"


def test_network_error_message_has_no_token():
    sess = _Sess(routes={"": [requests.ConnectionError(f"boom {FAKE}")]})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).whoami()
    assert exc.value.kind == "network"
    assert FAKE not in str(exc.value)


def test_reads_retry_on_network_error_then_succeed():
    err = requests.ConnectionError("down")
    sess = _Sess(routes={"": [err, err, _Resp(body={"id": "u"})]})
    assert _client(sess).whoami() == "u"
    assert len(sess.calls) == 3


def test_reads_give_up_after_retries():
    err = requests.ConnectionError("down")
    sess = _Sess(routes={"": [err]})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).whoami()
    assert exc.value.kind == "network"
    assert len(sess.calls) == 3
