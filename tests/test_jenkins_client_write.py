import pytest
import requests

from runtime.jenkins.client import BuildCancelled, JenkinsClient, JenkinsError

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
    """路由键是 "METHOD url" 的子串；响应列表依次消耗，最后一个重复使用。"""

    def __init__(self, routes):
        self.routes = {k: (list(v) if isinstance(v, list) else [v]) for k, v in routes.items()}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for key in sorted(self.routes, key=len, reverse=True):
            if key in f"{method} {url}":
                queue = self.routes[key]
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"未预期的请求 {method} {url}")

    def methods(self, method):
        return [c for c in self.calls if c[0] == method]


def _client(sess):
    return JenkinsClient(BASE, "u", FAKE, session=sess, retry_delay=0, sleep=lambda s: None)


QUEUE = f"{BASE}/queue/item/12/"


def test_trigger_with_params_posts_build_with_parameters():
    sess = _Sess({"POST": _Resp(201, headers={"Location": QUEUE})})
    assert _client(sess).trigger("job1", {"BRANCH": "feature/x"}) == QUEUE
    method, url, kwargs = sess.calls[0]
    assert method == "POST"
    assert url.endswith("/job/job1/buildWithParameters")
    assert kwargs["data"] == {"BRANCH": "feature/x"}


def test_trigger_without_params_uses_build_endpoint():
    sess = _Sess({"POST": _Resp(201, headers={"Location": QUEUE})})
    client = _client(sess)
    client.trigger("job1", None)
    client.trigger("job1", {})
    assert sess.calls[0][1].endswith("/job/job1/build")
    assert sess.calls[1][1].endswith("/job/job1/buildWithParameters")


def test_trigger_missing_location_raises_queue_error():
    sess = _Sess({"POST": _Resp(201)})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).trigger("job1", None)
    assert exc.value.kind == "queue"


def test_trigger_retries_once_with_crumb_on_403_crumb_error():
    sess = _Sess({
        "POST": [
            _Resp(403, text="No valid crumb was included in the request"),
            _Resp(201, headers={"Location": QUEUE}),
        ],
        "crumbIssuer": _Resp(body={"crumbRequestField": "Jenkins-Crumb", "crumb": "c1"}),
    })
    assert _client(sess).trigger("job1", {"A": "1"}) == QUEUE
    posts = sess.methods("POST")
    assert len(posts) == 2
    assert posts[1][2]["headers"]["Jenkins-Crumb"] == "c1"


def test_trigger_crumb_retry_happens_only_once():
    sess = _Sess({
        "POST": _Resp(403, text="No valid crumb was included in the request"),
        "crumbIssuer": _Resp(body={"crumbRequestField": "Jenkins-Crumb", "crumb": "c1"}),
    })
    with pytest.raises(JenkinsError) as exc:
        _client(sess).trigger("job1", None)
    assert exc.value.kind == "permission"
    assert len(sess.methods("POST")) == 2


def test_trigger_plain_403_is_permission_and_not_retried():
    sess = _Sess({"POST": _Resp(403, text="forbidden")})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).trigger("job1", None)
    assert exc.value.kind == "permission"
    assert "job1" in str(exc.value)
    assert len(sess.methods("POST")) == 1


def test_trigger_network_error_not_retried():
    sess = _Sess({"POST": requests.ConnectionError(f"down {FAKE}")})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).trigger("job1", None)
    assert exc.value.kind == "network"
    assert FAKE not in str(exc.value)
    assert len(sess.methods("POST")) == 1


def test_wait_for_build_returns_number_after_polling():
    sleeps = []
    sess = _Sess({"queue/item/12": [
        _Resp(body={"executable": None}),
        _Resp(body={"executable": None}),
        _Resp(body={"executable": {"number": 57}}),
    ]})
    client = JenkinsClient(BASE, "u", FAKE, session=sess, sleep=sleeps.append)
    assert client.wait_for_build(QUEUE, timeout_s=60) == 57
    assert len(sleeps) == 2
    assert sess.calls[0][1] == f"{BASE}/queue/item/12/api/json"


def test_wait_for_build_cancelled_and_timeout():
    cancelled = _Sess({"queue/item/12": _Resp(body={"cancelled": True})})
    with pytest.raises(BuildCancelled) as exc:
        _client(cancelled).wait_for_build(QUEUE, timeout_s=60)
    assert exc.value.kind == "queue"

    stuck = _Sess({"queue/item/12": _Resp(body={"executable": None})})
    with pytest.raises(JenkinsError) as exc:
        _client(stuck).wait_for_build(QUEUE, timeout_s=0)
    assert exc.value.kind == "timeout"


def _status(building, result=None):
    return _Resp(body={"number": 57, "building": building, "result": result, "url": f"{BASE}/job/job1/57/"})


def test_wait_finished_polls_until_not_building():
    sess = _Sess({"/57/api/json": [_status(True), _status(True), _status(False, "SUCCESS")]})
    status = _client(sess).wait_finished("job1", 57, timeout_s=60)
    assert (status.building, status.result) == (False, "SUCCESS")
    assert len(sess.calls) == 3


def test_wait_finished_timeout_carries_build_url():
    sess = _Sess({"/57/api/json": _status(True)})
    with pytest.raises(JenkinsError) as exc:
        _client(sess).wait_finished("job1", 57, timeout_s=0)
    assert exc.value.kind == "timeout"
    assert exc.value.url == f"{BASE}/job/job1/57/"


def test_queue_items_parses_job_params_and_folder_job():
    sess = _Sess({"/queue/api/json": _Resp(body={"items": [
        {"id": 3, "params": "BRANCH=dev", "task": {"name": "oms", "url": f"{BASE}/job/erp/job/oms/"}},
        {"id": 4, "params": "", "task": {"name": "pay", "url": f"{BASE}/job/pay/"}},
    ]})})
    items = _client(sess).queue_items()
    assert [(i.job, i.params, i.item_id) for i in items] == [
        ("erp/oms", {"BRANCH": "dev"}, 3),
        ("pay", {}, 4),
    ]


def test_in_flight_lists_queue_items_and_running_builds_for_job():
    sess = _Sess({
        "/queue/api/json": _Resp(body={"items": [
            {"id": 3, "params": "BRANCH=dev", "task": {"name": "order", "url": f"{BASE}/job/order/"}},
            {"id": 5, "params": "BRANCH=dev", "task": {"name": "other", "url": f"{BASE}/job/other/"}},
        ]}),
        "/job/order/api/json": _Resp(body={"builds": [
            {"number": 57, "building": True, "queueId": 2, "actions": [
                {"_class": "hudson.model.ParametersAction",
                 "parameters": [{"name": "BRANCH", "value": "dev"}]},
            ]},
            {"number": 56, "building": False, "actions": []},
        ]}),
    })
    items = _client(sess).in_flight("order")
    assert [(i.kind, i.number, i.item_id, i.params) for i in items] == [
        ("queue", None, 3, {"BRANCH": "dev"}),
        ("build", 57, None, {"BRANCH": "dev"}),
    ]
    assert items[1].queue_id == 2


def test_cancel_queue_item_posts_cancel_item_with_id():
    sess = _Sess({"/queue/cancelItem": _Resp(200)})
    _client(sess).cancel_queue_item(12)
    method, url, kwargs = sess.calls[0]
    assert method == "POST"
    assert url == f"{BASE}/queue/cancelItem"
    assert kwargs["params"] == {"id": 12}


def test_stop_build_posts_stop():
    sess = _Sess({"/job/order/57/stop": _Resp(200)})
    _client(sess).stop_build("order", 57)
    assert sess.calls[0][1] == f"{BASE}/job/order/57/stop"
