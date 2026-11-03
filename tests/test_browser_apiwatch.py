import pytest

from pathlib import Path

from runtime.browser.apiwatch import (
    ApiWatchConfig,
    is_ignored,
    judge_body,
    judge_status,
)
from runtime.browser.config import FlowDef, VarDef
from runtime.browser.flow import run_flow

CFG = ApiWatchConfig()


def test_http_error_on_xhr_and_fetch_is_failure():
    assert "HTTP 500" in judge_status(500, "xhr", CFG)
    assert "HTTP 404" in judge_status(404, "fetch", CFG)


def test_main_frame_document_error_is_failure():
    assert "HTTP 502" in judge_status(502, "document", CFG)


def test_static_asset_errors_and_success_are_ignored():
    assert judge_status(404, "image", CFG) is None
    assert judge_status(404, "other", CFG) is None
    assert judge_status(200, "xhr", CFG) is None
    assert judge_status(304, "fetch", CFG) is None


@pytest.mark.parametrize("code", [0, 200, "0", "200", "OK", "success", "SUCCESS"])
def test_business_success_codes_pass(code):
    assert judge_body(f'{{"code": {_json(code)}, "msg": "x"}}', CFG) is None


def test_business_error_code_reports_code_and_message():
    reason = judge_body('{"code": 500, "msg": "库存不足"}', CFG)
    assert "500" in reason and "库存不足" in reason


def test_success_false_is_failure():
    assert "库存不足" in judge_body('{"success": false, "message": "库存不足"}', CFG)


@pytest.mark.parametrize("body", ["{}", "[1, 2]", "plain text", "", '{"data": {"code": 500}}', "{bad json"])
def test_bodies_without_top_level_verdict_are_ignored(body):
    assert judge_body(body, CFG) is None


def test_custom_success_codes_replace_defaults():
    cfg = ApiWatchConfig(success_codes=("1",))
    assert judge_body('{"code": 1}', cfg) is None
    assert judge_body('{"code": 200}', cfg) is not None


def test_ignore_matches_url_substring():
    cfg = ApiWatchConfig(ignore=("/api/heartbeat",))
    assert is_ignored("http://x/api/heartbeat?t=1", cfg)
    assert not is_ignored("http://x/api/save", cfg)


def _json(value):
    return f'"{value}"' if isinstance(value, str) else str(value)


def make_flow(*steps):
    return FlowDef(
        name="test",
        description="",
        env="dev",
        vars={"order_no": VarDef(True, None, "")},
        steps=list(steps),
        path=Path("test.yaml"),
    )


def run(page, tmp_path, flow, timeout_ms=20000, api_watch=None):
    kwargs = {} if api_watch is None else {"api_watch": api_watch}
    return run_flow(page, flow, "dev", {"order_no": "WO001"}, tmp_path, timeout_ms=timeout_ms, **kwargs)


def open_page(fixture_url):
    return {"name": "打开", "goto": fixture_url + "/apierr.html"}


def test_http_500_fails_fast_instead_of_waiting_for_timeout(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "boom"}, "wait_visible": {"css": "#done"}},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "fail"
    assert result.failure.step_name == "触发"
    assert "接口异常" in result.failure.message and "500" in result.failure.message
    assert result.failure.detail["api_errors"][0]["status"] == 500
    assert "/api/boom" in result.failure.detail["api_errors"][0]["url"]
    assert result.duration_ms < 8000


def test_business_error_with_http_200_fails_fast(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "biz"}, "expect_visible": {"css": "#done"}},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "fail"
    assert "库存不足" in result.failure.message
    assert result.duration_ms < 8000


def test_wait_response_on_non_2xx_fails_immediately(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "boom"}, "wait_response": "/api/boom"},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "fail"
    assert "500" in result.failure.message
    assert result.duration_ms < 5000


def test_wait_response_on_business_error_fails_immediately(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "biz"}, "wait_response": "/api/biz-error"},
    )
    result = run(page, tmp_path, flow)
    assert result.result == "fail"
    assert "库存不足" in result.failure.message


def test_error_followed_by_recovery_within_grace_passes(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "noisy"}, "wait_visible": {"css": "#done"}},
    )
    assert run(page, tmp_path, flow, timeout_ms=5000).result == "pass"


def test_allow_api_error_skips_the_watch_for_that_step(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "boom"}, "allow_api_error": ["/api/boom"],
         "expect_visible": {"css": "#done"}},
    )
    result = run(page, tmp_path, flow, timeout_ms=800)
    assert result.result == "fail"
    assert "接口异常" not in result.failure.message


def test_disabled_watch_falls_back_to_plain_timeout(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "boom"}, "expect_visible": {"css": "#done"}},
    )
    result = run(page, tmp_path, flow, timeout_ms=800, api_watch=ApiWatchConfig(enabled=False))
    assert result.result == "fail"
    assert "接口异常" not in result.failure.message


def test_ignored_url_falls_back_to_plain_timeout(page, fixture_url, tmp_path):
    flow = make_flow(
        open_page(fixture_url),
        {"name": "触发", "click": {"testid": "boom"}, "expect_visible": {"css": "#done"}},
    )
    result = run(page, tmp_path, flow, timeout_ms=800, api_watch=ApiWatchConfig(ignore=("/api/boom",)))
    assert result.result == "fail"
    assert "接口异常" not in result.failure.message
