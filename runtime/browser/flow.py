"""浏览器流程执行引擎。"""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlparse

from runtime.config import ConfigError, data_home, substitute

from .apiwatch import ApiFailure, ApiWatch, ApiWatchConfig
from .config import FlowDef, LoginConfig
from .display import check_display
from .driver import check_login_success, page_closed
from .locator import LocatorMatchError, find, find_all
from .watch import WatchController


class FlowRunError(Exception):
    pass


class _StepSkipped(Exception):
    pass


class StepAssertion(Exception):
    def __init__(
        self,
        message: str,
        expected: str | None = None,
        actual: str | None = None,
        detail: dict | None = None,
    ):
        self.expected = expected
        self.actual = actual
        self.detail = dict(detail or {})
        super().__init__(message)


@dataclass
class StepResult:
    name: str
    status: str
    duration_ms: int
    error: str | None = None


@dataclass
class StepFailure:
    step_index: int
    step_name: str
    message: str
    expected: str | None = None
    actual: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class FlowResult:
    flow: str
    env: str
    result: str
    started_at: str
    duration_ms: int
    flow_file: str
    steps: list[StepResult]
    failure: StepFailure | None = None
    artifacts: str | None = None
    error: str | None = None


_ACTIONS = {"goto", "click", "fill", "press", "select", "check", "hover", "use_row", "impl"}
_LOCATOR_ACTIONS = {"click", "fill", "select", "check", "hover"}


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _log(logger: Any, message: str) -> None:
    if logger is not None:
        try:
            logger.info(message)
        except Exception:
            pass


def _wait_until(
    predicate: Callable[[], Any],
    timeout_ms: int,
    interval: float = 0.05,
    watch: ApiWatch | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        try:
            if predicate():
                return True
        except Exception as exc:
            # 页面/浏览器已被关闭，再等也不会好：立刻抛出，别等满超时。
            # 按类名判断，避免 flow.py 依赖 playwright 的内部异常模块。
            if type(exc).__name__ == "TargetClosedError":
                raise
        if watch is not None:
            watch.check()
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def _text(locator: Any) -> str:
    try:
        return locator.inner_text()
    except Exception:
        try:
            return locator.text_content() or ""
        except Exception:
            return ""


def _first(locator: Any) -> Any:
    try:
        return locator.first
    except Exception:
        return locator


def _row_locator(page: Any, spec: dict) -> Any:
    row = page.locator(spec.get("row_css", "table tbody tr"))
    if spec.get("checkbox"):
        row = row.filter(has=page.locator(spec["checkbox"]))
    if spec.get("text"):
        row = row.filter(has_text=spec["text"])
    return row


def _target_locator(page: Any, step: dict, aliases: dict[str, Any]) -> Any | None:
    if "use_row" in step:
        return _row_locator(page, step["use_row"])
    for action in _LOCATOR_ACTIONS:
        if action in step:
            return find(page, step[action], aliases)
    return None


def _response_predicate(value: Any, any_status: bool = False) -> Callable[[Any], bool]:
    """any_status：接口监听开启时，响应一到就匹配（状态异常交给 watch.verify 立即判失败），不再傻等一个 2xx。"""
    if isinstance(value, str):
        def match(response: Any) -> bool:
            return value in response.url and (any_status or 200 <= response.status < 300)

        return match

    value = value or {}
    url_part = value.get("url_contains", "")
    status = value.get("status")

    def match(response: Any) -> bool:
        if url_part and url_part not in response.url:
            return False
        if status is not None:
            return response.status == status
        return any_status or 200 <= response.status < 300

    return match


STABLE_POLLS = 4
STABLE_INTERVAL = 0.06


def _wait_stable(locator: Any, timeout_ms: int) -> None:
    """等元素的位置和大小连续几次不变；异步布局期间点击会落在旧坐标上。超时不报错，交给后续动作判断。"""
    deadline = time.monotonic() + timeout_ms / 1000
    last = None
    same = 0
    while time.monotonic() < deadline:
        try:
            box = _first(locator).bounding_box()
        except Exception:
            box = None
        if box is not None and box == last:
            same += 1
            if same >= STABLE_POLLS:
                return
        else:
            same = 0
        last = box
        time.sleep(STABLE_INTERVAL)


WATCH_SLICE_MS = 300


def _wait_for_state(locator: Any, state: str, timeout_ms: int, watch: ApiWatch | None) -> None:
    """locator.wait_for 的可中断版本：分片等待，片与片之间检查接口异常；最后一片超时照常抛 Playwright 原始错误。"""
    if watch is None:
        locator.wait_for(state=state, timeout=timeout_ms)
        return
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        remaining = int((deadline - time.monotonic()) * 1000)
        try:
            locator.wait_for(state=state, timeout=max(1, min(WATCH_SLICE_MS, remaining)))
            return
        except Exception as exc:
            if type(exc).__name__ != "TimeoutError" or remaining <= WATCH_SLICE_MS:
                raise
        watch.check()


def load_impl(spec: str, root: Path) -> Callable:
    try:
        file_part, func_name = spec.split(":", 1)
    except ValueError as exc:
        raise FlowRunError(f"impl 必须写成 文件:函数：{spec}") from exc
    path = Path(root) / file_part
    if not path.exists():
        raise FlowRunError(f"impl 文件不存在：{path}")
    module_spec = importlib.util.spec_from_file_location(f"browser_impl_{abs(hash(path))}", path)
    if module_spec is None or module_spec.loader is None:
        raise FlowRunError(f"无法加载 impl：{path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    func = getattr(module, func_name, None)
    if func is None:
        raise FlowRunError(f"{path} 中没有函数 {func_name}")
    return func


def _target(page: Any, spec: dict, aliases: dict[str, Any]) -> Any:
    """定位动作目标，并等它的位置稳定后再返回，避免异步布局期间点在旧坐标上。"""
    locator = find(page, spec, aliases)
    _wait_stable(locator, 3000)
    return locator


def _perform(
    page: Any,
    step: dict,
    variables: dict[str, str],
    aliases: dict[str, Any],
    project_dir: Path,
    logger: Any,
) -> Any | None:
    if "goto" in step:
        page.goto(str(step["goto"]), wait_until="domcontentloaded")
    elif "click" in step:
        _target(page, step["click"], aliases).click()
    elif "fill" in step:
        _target(page, step["fill"], aliases).fill(str(step["value"]))
    elif "press" in step:
        page.keyboard.press(str(step["press"]))
    elif "select" in step:
        _target(page, step["select"], aliases).select_option(str(step["value"]))
    elif "check" in step:
        _target(page, step["check"], aliases).check()
    elif "hover" in step:
        _target(page, step["hover"], aliases).hover()
    elif "use_row" in step:
        row = _row_locator(page, step["use_row"])
        if step.get("as"):
            aliases[step["as"]] = row
        return row
    elif "impl" in step:
        func = load_impl(str(step["impl"]), project_dir)
        ctx = SimpleNamespace(
            page=page,
            vars=variables,
            project_dir=Path(project_dir),
            data_home=data_home(),
            logger=logger,
            step=step,
        )
        result = func(ctx)
        if isinstance(result, dict):
            variables.update({str(key): str(value) for key, value in result.items()})
        return result
    return None


def _apply_waits(
    page: Any,
    step: dict,
    aliases: dict[str, Any],
    target: Any | None,
    timeout_ms: int,
    watch: ApiWatch | None = None,
) -> None:
    if "wait_url" in step:
        value = step["wait_url"]
        if isinstance(value, str):
            value = {"contains": value}
        if "path" in value:
            expected = f"pathname={value['path']}"
            ok = _wait_until(lambda: urlparse(page.url).path == value["path"], timeout_ms, watch=watch)
        else:
            contains = str(value.get("contains", ""))
            expected = f"URL 包含 {contains}"
            ok = _wait_until(lambda: contains in page.url, timeout_ms, watch=watch)
        if not ok:
            raise StepAssertion("等待 URL 超时", expected, page.url)

    if "wait_visible" in step:
        value = step["wait_visible"]
        if value is True:
            locator = aliases.get(step.get("as")) or target
            if locator is None:
                raise StepAssertion("wait_visible=true 需要 as 或 use_row")
            _wait_for_state(_first(locator), "visible", timeout_ms, watch)
        else:
            _wait_for_state(find(page, value, aliases), "visible", timeout_ms, watch)

    if "wait_hidden" in step:
        _wait_for_state(find(page, step["wait_hidden"], aliases), "hidden", timeout_ms, watch)

    if "wait_text" in step:
        value = step["wait_text"]
        locator = find(page, value["locator"], aliases)
        _expect_text(locator, value, timeout_ms, watch)


def _expect_text(locator: Any, value: dict, timeout_ms: int, watch: ApiWatch | None = None) -> None:
    expected = value.get("equals")
    contains = value.get("contains")
    expected_text = f"等于 {expected}" if expected is not None else f"包含 {contains}"
    actual = ""
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        actual = _text(locator)
        if expected is not None and actual == expected:
            return
        if expected is None and contains is not None and contains in actual:
            return
        if watch is not None:
            watch.check()
        if time.monotonic() >= deadline:
            raise StepAssertion(f"文本断言失败：期望 {expected_text}，实际 {actual!r}", expected_text, actual)
        time.sleep(0.05)


def _apply_expects(
    page: Any,
    step: dict,
    aliases: dict[str, Any],
    timeout_ms: int,
    watch: ApiWatch | None = None,
) -> None:
    if "expect_visible" in step:
        locator = find(page, step["expect_visible"], aliases)
        if not _wait_until(lambda: locator.is_visible(), timeout_ms, watch=watch):
            raise StepAssertion("元素未可见", "可见", "不可见")

    if "expect_hidden" in step:
        locator = find(page, step["expect_hidden"], aliases)
        if not _wait_until(lambda: not locator.is_visible(), timeout_ms, watch=watch):
            raise StepAssertion("元素仍可见", "不可见", "可见")

    if "expect_text" in step:
        value = step["expect_text"]
        _expect_text(find(page, value["locator"], aliases), value, timeout_ms, watch)

    if "expect_url" in step:
        value = step["expect_url"]
        if "path" in value:
            expected = f"pathname={value['path']}"
            ok = _wait_until(lambda: urlparse(page.url).path == value["path"], timeout_ms, watch=watch)
        else:
            contains = str(value.get("contains", ""))
            expected = f"URL 包含 {contains}"
            ok = _wait_until(lambda: contains in page.url, timeout_ms, watch=watch)
        if not ok:
            raise StepAssertion("URL 断言失败", expected, page.url)

    if "expect_count" in step:
        value = step["expect_count"]
        locator = find_all(page, value["locator"], aliases)
        eq = value.get("eq")
        minimum = value.get("min")
        maximum = value.get("max")
        expected = f"数量 eq={eq} min={minimum} max={maximum}"

        def count_ok() -> bool:
            count = locator.count()
            if eq is not None and count != eq:
                return False
            if minimum is not None and count < minimum:
                return False
            if maximum is not None and count > maximum:
                return False
            return True

        if not _wait_until(count_ok, timeout_ms, watch=watch):
            raise StepAssertion("元素数量断言失败", expected, str(locator.count()))

    if "expect_display" in step:
        check_display(page, step["expect_display"], aliases, timeout_ms, watch)


def run_step(
    page: Any,
    step: dict,
    variables: dict[str, str],
    aliases: dict[str, Any],
    project_dir: Path,
    *,
    timeout_ms: int,
    logger: Any = None,
    watch: ApiWatch | None = None,
) -> None:
    step = substitute(step, variables)
    action = next((key for key in step if key in _ACTIONS), None)
    if action is None and "wait_response" in step:
        raise FlowRunError("wait_response 需要动作")

    if action is None:
        target = None
    else:
        if step.get("optional"):
            target = _target_locator(page, step, aliases)
            if target is not None and target.count() == 0:
                raise _StepSkipped()
        wait_response = step.get("wait_response")
        if wait_response:
            predicate = _response_predicate(wait_response, any_status=watch is not None and watch.active)
            with page.expect_response(predicate, timeout=timeout_ms) as response_info:
                target = _perform(page, step, variables, aliases, project_dir, logger)
            response = response_info.value
            _log(logger, f"{step.get('name')}: response {response.status} {response.url}")
            if watch is not None and not (isinstance(wait_response, dict) and "status" in wait_response):
                watch.verify(response)
        else:
            target = _perform(page, step, variables, aliases, project_dir, logger)

    _apply_waits(page, step, aliases, target, timeout_ms, watch)
    _apply_expects(page, step, aliases, timeout_ms, watch)


def _failure_from_exception(index: int, name: str, exc: Exception) -> StepFailure:
    if isinstance(exc, (StepAssertion, ApiFailure)):
        return StepFailure(index, name, str(exc), exc.expected, exc.actual, exc.detail)
    if isinstance(exc, LocatorMatchError):
        return StepFailure(
            index,
            name,
            str(exc),
            "唯一元素",
            f"命中 {exc.count} 个",
            {"count": exc.count, "candidates": exc.candidates},
        )
    return StepFailure(index, name, str(exc), detail={"type": type(exc).__name__})


def run_flow(
    page: Any,
    flow: FlowDef,
    env_name: str,
    variables: dict[str, str],
    project_dir: Path,
    *,
    timeout_ms: int = 15000,
    logger: Any = None,
    api_watch: ApiWatchConfig | None = None,
    pacer: WatchController | None = None,
) -> FlowResult:
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.monotonic()
    values = dict(variables)
    aliases: dict[str, Any] = {}
    results: list[StepResult] = []
    failure: StepFailure | None = None
    watch = ApiWatch(api_watch or ApiWatchConfig())
    watch.attach(page)

    try:
        for index, step in enumerate(flow.steps, 1):
            name = str(step.get("name", f"步骤{index}"))
            if pacer is not None:
                pacer.pace(f"步骤 {index}/{len(flow.steps)}：{name}")
            step_started = time.monotonic()
            step_timeout = int(step.get("timeout", timeout_ms))
            watch.begin_step(step.get("allow_api_error", False))
            try:
                run_step(
                    page,
                    step,
                    values,
                    aliases,
                    Path(project_dir),
                    timeout_ms=step_timeout,
                    logger=logger,
                    watch=watch,
                )
            except _StepSkipped:
                results.append(StepResult(name, "skipped", _ms(step_started)))
                _log(logger, f"{name}: skipped")
                continue
            except Exception as exc:
                failure = _failure_from_exception(index, name, exc)
                results.append(StepResult(name, "fail", _ms(step_started), str(exc)))
                _log(logger, f"{name}: fail {exc}")
                break
            results.append(StepResult(name, "pass", _ms(step_started)))
            _log(logger, f"{name}: pass")
    finally:
        watch.detach()

    return FlowResult(
        flow=flow.name,
        env=env_name,
        result="fail" if failure else "pass",
        started_at=started_at,
        duration_ms=_ms(started),
        flow_file=str(flow.path),
        steps=results,
        failure=failure,
    )


def _login_ready(page: Any, login: LoginConfig, login_path: str) -> bool:
    try:
        if check_login_success(page, login):
            return True
        if urlparse(page.url).path == login_path:
            return page.locator("input, button").count() > 0
    except Exception:
        return False
    return False


def ensure_login(
    page: Any,
    login: LoginConfig,
    *,
    variables: dict[str, str],
    project_dir: Path,
    timeout_ms: int = 15000,
    logger: Any = None,
    pacer: WatchController | None = None,
) -> bool:
    values = dict(variables)
    try:
        url = substitute(login.url, values)
    except ConfigError as exc:
        raise FlowRunError(f"登录地址变量解析失败：{exc}") from exc

    login_path = urlparse(str(url)).path
    if pacer is not None:
        pacer.pace("登录：打开登录页")
    page.goto(str(url), wait_until="domcontentloaded")
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if page_closed(page):
            raise FlowRunError("测试浏览器已被关闭，登录中断")
        if check_login_success(page, login):
            return True
        if _login_ready(page, login, login_path):
            break
        time.sleep(0.1)

    login_values = {
        **values,
        "username": login.username or "",
        "password": login.password or "",
    }
    if login.impl:
        if pacer is not None:
            pacer.pace("登录：自定义登录")
        func = load_impl(login.impl, Path(project_dir))
        ctx = SimpleNamespace(
            page=page,
            vars=login_values,
            project_dir=Path(project_dir),
            data_home=data_home(),
            logger=logger,
            step={"impl": login.impl},
        )
        result = func(ctx)
        if isinstance(result, dict):
            login_values.update({str(key): str(value) for key, value in result.items()})
    else:
        for index, raw_step in enumerate(login.steps, 1):
            step = dict(raw_step)
            step.setdefault("name", f"登录步骤{index}")
            if pacer is not None:
                pacer.pace(f"登录 {index}/{len(login.steps)}：{step['name']}")
            try:
                run_step(
                    page,
                    step,
                    login_values,
                    {},
                    Path(project_dir),
                    timeout_ms=timeout_ms,
                    logger=logger,
                )
            except _StepSkipped:
                continue
            except Exception as exc:
                if check_login_success(page, login):
                    return True
                raise FlowRunError(f"登录步骤失败：{step['name']}：{exc}") from exc
            if check_login_success(page, login):
                return True

    if _wait_until(lambda: check_login_success(page, login), timeout_ms):
        return True
    raise FlowRunError("登录失败：未检测到登录成功标志")
