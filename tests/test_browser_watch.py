import pytest

from runtime.browser import watch as watch_mod
from runtime.browser.watch import ImplWatch, WatchController


class FakePage:
    def __init__(self):
        self.drains = []
        self.calls = []
        self.closed = False
        self.context = self

    def add_init_script(self, script):
        self.calls.append(("init", script))

    def evaluate(self, script, arg=None):
        self.calls.append((script, arg))
        if script is watch_mod._DRAIN_JS:
            return self.drains.pop(0) if self.drains else []
        return None

    def is_closed(self):
        return self.closed

    def states(self):
        return [arg for script, arg in self.calls if script is watch_mod._SET_JS and arg]


class FakeLocator:
    def __init__(self, box=(10, 20, 100, 30), summary="提交订单"):
        self.box = box
        self.summary = summary
        self.calls = []

    def scroll_into_view_if_needed(self, timeout=None):
        self.calls.append(("scroll", timeout))

    def bounding_box(self):
        if isinstance(self.box, Exception):
            raise self.box
        if self.box is None:
            return None
        x, y, width, height = self.box
        return {"x": x, "y": y, "width": width, "height": height}

    def evaluate(self, script):
        self.calls.append(("evaluate", script))
        if isinstance(self.summary, Exception):
            raise self.summary
        return self.summary


def test_pace_waits_one_action_interval():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)

    controller.pace("步骤 1/3：打开")

    assert sleeps == [1.5]
    assert controller.delay_ms == 1500
    assert controller.speed_text == "1.5s"
    assert page.states()[-1] == {
        "label": "步骤 1/3：打开",
        "speed": "1.5s",
        "paused": False,
        "ended": False,
    }


def test_speed_buttons_change_pace_and_clamp():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)

    page.drains = [["slower"]]
    controller.pace("慢")
    page.drains = [["slower"] * 4]
    controller.pace("更慢")

    assert controller.speed_index == len(watch_mod.SPEEDS_MS) - 1
    assert controller.delay_ms == 2500

    page.drains = [["faster"] * 5]
    controller.pace("快")

    assert controller.speed_index == 0
    assert sleeps == [2.5, 2.5, 0.2]


def test_pause_waits_until_resume_without_extra_delay():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)
    controller.paused = True
    page.drains = [[], ["toggle"]]

    controller.pace("步骤 2/5：填单")

    assert controller.paused is False
    assert 0.8 not in sleeps
    assert sleeps == [controller.poll_interval]
    assert any(state["label"] == "已暂停 · 步骤 2/5：填单" for state in page.states())


def test_pause_releases_when_page_is_closed():
    page = FakePage()
    page.closed = True
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.paused = True

    controller.pace("步骤 3/5：审核")

    assert controller.paused is True


def test_beat_waits_one_interval_without_changing_label():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)
    controller.label = "步骤 1/1：加工"

    controller.beat()

    assert sleeps == [1.5]
    assert controller.label == "步骤 1/1：加工"


def test_beat_waits_until_resume():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)
    controller.paused = True
    page.drains = [[], ["toggle"]]

    controller.beat()

    assert controller.paused is False
    assert sleeps == [controller.poll_interval]


def test_finish_switches_bar_to_end_state():
    page = FakePage()
    controller = WatchController(page, sleep=lambda seconds: None)

    controller.finish("演示结束 · 通过")

    assert controller.ended is True
    assert controller.paused is False
    assert page.states()[-1] == {
        "label": "演示结束 · 通过",
        "speed": "1.5s",
        "paused": False,
        "ended": True,
    }


def test_wait_close_returns_after_close_button_click():
    page = FakePage()
    sleeps = []
    page.drains = [[], ["close"]]
    controller = WatchController(page, sleep=sleeps.append)

    controller.wait_close()

    assert sleeps == [controller.poll_interval]


def test_wait_close_returns_immediately_when_window_is_closed():
    page = FakePage()
    page.closed = True
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)

    controller.wait_close()

    assert sleeps == []


def test_wait_close_gives_up_when_page_keeps_failing():
    class BrokenPage:
        def evaluate(self, script):
            raise RuntimeError("page crashed")

        def is_closed(self):
            return False

    sleeps = []
    controller = WatchController(BrokenPage(), sleep=sleeps.append)

    controller.wait_close()

    assert 0 < len(sleeps) <= watch_mod._MAX_DRAIN_FAILURES


def test_attach_installs_bar_now_and_on_future_navigation():
    page = FakePage()
    controller = WatchController(page, sleep=lambda seconds: None)

    controller.attach()

    assert any(kind == "init" for kind, _ in page.calls)
    assert (watch_mod._INSTALL_JS, None) in page.calls
    assert page.states()


def test_hide_and_show_update_the_bar():
    page = FakePage()
    controller = WatchController(page, sleep=lambda seconds: None)

    controller.hide()
    controller.show()

    scripts = [script for script, _ in page.calls]
    assert watch_mod._HIDE_JS in scripts
    assert watch_mod._SHOW_JS in scripts


def test_control_bar_is_injected_into_real_page(page, fixture_url):
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.attach()
    page.goto(fixture_url + "/index.html")

    assert page.evaluate("() => !!window.__dataToolsWatch") is True
    label = page.evaluate(
        "() => document.querySelector('#__data-tools-watch')"
        ".shadowRoot.querySelector('.label').textContent"
    )
    assert label  # 新页面加载后控制条自动重建


def test_slower_button_in_browser_is_picked_up(page, fixture_url):
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.attach()
    page.goto(fixture_url + "/index.html")

    page.locator("#__data-tools-watch [data-act=slower]").click()
    sleeps = []
    controller._sleep = sleeps.append
    controller.pace("下一步")

    assert controller.delay_ms == 2500
    assert sleeps == [2.5]


def test_bar_click_keeps_dropdown_open_and_focus(page):
    page.set_content(
        """
        <button id="opener">选择仓库</button>
        <div id="dropdown" hidden><div role="option" id="option">海洋研发样品仓</div></div>
        <script>
          const opener = document.querySelector('#opener');
          const dropdown = document.querySelector('#dropdown');
          opener.addEventListener('click', () => {
            dropdown.hidden = false;
          });
          document.addEventListener('click', (event) => {
            if (opener.contains(event.target) || dropdown.contains(event.target)) return;
            dropdown.hidden = true;
          }, true);
        </script>
        """
    )
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.attach()

    page.click("#opener")
    assert page.evaluate("() => !document.querySelector('#dropdown').hidden") is True

    page.locator("#__data-tools-watch [data-act=slower]").click()

    assert page.evaluate("() => !document.querySelector('#dropdown').hidden") is True
    assert page.evaluate(
        "() => document.activeElement && document.activeElement.id"
    ) == "opener"


def test_highlight_draws_box_and_waits_lead_before_action():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)
    locator = FakeLocator()

    controller.highlight(locator, "点击")

    assert locator.calls[0] == ("scroll", 1500)
    args = [arg for script, arg in page.calls if script is watch_mod._HIGHLIGHT_JS]
    assert args[-1] == {
        "x": 10.0,
        "y": 20.0,
        "width": 100.0,
        "height": 30.0,
        "text": "点击 · 提交订单",
        "hold_ms": 1400,
    }
    assert sleeps == [controller.lead_seconds]


def test_highlight_lead_follows_speed():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, speed_index=0, sleep=sleeps.append)

    controller.highlight(FakeLocator(), "输入")

    assert controller.delay_ms == 200
    assert sleeps == [0.1]


def test_highlight_falls_back_to_verb_without_element_text():
    page = FakePage()
    controller = WatchController(page, sleep=lambda seconds: None)

    controller.highlight(FakeLocator(summary=""), "点击")

    args = [arg for script, arg in page.calls if script is watch_mod._HIGHLIGHT_JS]
    assert args[-1]["text"] == "点击"


def test_highlight_failure_is_silent_and_does_not_delay_action():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)

    controller.highlight(FakeLocator(box=RuntimeError("element detached")), "点击")
    controller.highlight(FakeLocator(box=None), "点击")
    controller.highlight(FakeLocator(summary=RuntimeError("页面已关闭")), "点击")

    assert not [script for script, _ in page.calls if script is watch_mod._HIGHLIGHT_JS]
    assert sleeps == []


def test_highlight_overlay_is_click_through_and_disappears(page):
    page.set_content('<button id="buy" style="margin:40px;padding:10px">提交订单</button>')
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.attach()

    controller.highlight(page.locator("#buy"), "点击")

    assert page.evaluate("() => !!document.querySelector('#__data-tools-highlight')") is True
    label = page.evaluate(
        "() => document.querySelector('#__data-tools-highlight')"
        ".shadowRoot.querySelector('.label').textContent"
    )
    assert label == "点击 · 提交订单"
    assert page.evaluate(
        "() => getComputedStyle(document.querySelector('#__data-tools-highlight')).pointerEvents"
    ) == "none"

    page.click("#buy")  # 高亮层不能拦住动作本身的点击
    page.wait_for_function(
        "() => !document.querySelector('#__data-tools-highlight')", timeout=3000
    )


def test_finish_shows_close_button_in_browser(page):
    page.set_content("<p>演示结果</p>")
    controller = WatchController(page, sleep=lambda seconds: None)
    controller.attach()

    controller.finish("演示结束 · 通过")

    label = page.evaluate(
        "() => document.querySelector('#__data-tools-watch')"
        ".shadowRoot.querySelector('.label').textContent"
    )
    assert label == "演示结束 · 通过"
    assert page.locator("#__data-tools-watch [data-act=close]").is_visible()
    assert page.locator("#__data-tools-watch [data-act=toggle]").is_visible() is False

    page.locator("#__data-tools-watch [data-act=close]").click()

    assert "close" in controller._drain()


class RecordingLocator:
    def __init__(self):
        self.calls = []

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))
        return "clicked"

    def fill(self, value, **kwargs):
        self.calls.append(("fill", value, kwargs))
        return "filled"

    def select_option(self, value, **kwargs):
        self.calls.append(("select_option", value, kwargs))
        return "selected"

    def check(self, **kwargs):
        self.calls.append(("check", kwargs))
        return "checked"

    def hover(self, **kwargs):
        self.calls.append(("hover", kwargs))
        return "hovered"


class RecordingPage:
    def __init__(self, locator=None):
        self.locator_calls = []
        self.locator_obj = locator or RecordingLocator()

    def locator(self, selector):
        self.locator_calls.append(selector)
        return self.locator_obj


class RecordingController:
    def __init__(self):
        self.calls = []
        self.label = "步骤 1/1：加工"

    def pace(self, label):
        self.label = label
        self.calls.append(("pace", label))

    def beat(self):
        self.calls.append(("beat",))

    def highlight(self, locator, verb):
        self.calls.append(("highlight", locator, verb))


def test_impl_watch_click_beats_and_highlights_before_action():
    page = RecordingPage()
    controller = RecordingController()
    watch = ImplWatch(controller, page)

    result = watch.click("#save", timeout=1000)

    assert result == "clicked"
    assert page.locator_calls == ["#save"]
    assert controller.calls == [("beat",), ("highlight", page.locator_obj, "点击")]
    assert page.locator_obj.calls == [("click", {"timeout": 1000})]


@pytest.mark.parametrize(
    "invoke, expected_call, verb",
    [
        (lambda watch, target: watch.fill(target, "abc", timeout=5), ("fill", "abc", {"timeout": 5}), "输入"),
        (lambda watch, target: watch.select(target, "A"), ("select_option", "A", {}), "选择"),
        (lambda watch, target: watch.check(target, timeout=5), ("check", {"timeout": 5}), "勾选"),
        (lambda watch, target: watch.hover(target), ("hover", {}), "悬停"),
    ],
    ids=["fill", "select", "check", "hover"],
)
def test_impl_watch_maps_helper_to_playwright_action_and_verb(invoke, expected_call, verb):
    locator = RecordingLocator()
    page = RecordingPage(locator)
    controller = RecordingController()
    watch = ImplWatch(controller, page)

    invoke(watch, locator)

    assert locator.calls == [expected_call]
    assert controller.calls == [("beat",), ("highlight", locator, verb)]
    assert page.locator_calls == []


def test_impl_watch_without_controller_still_runs_actions():
    page = RecordingPage()
    watch = ImplWatch(None, page)

    assert watch.enabled is False
    assert watch.click("#save") == "clicked"
    assert page.locator_obj.calls == [("click", {})]


def test_impl_watch_manual_helpers_delegate_to_controller():
    page = RecordingPage()
    controller = RecordingController()
    watch = ImplWatch(controller, page)
    locator = page.locator_obj

    watch.pace("加工 · 等接口")
    watch.highlight(locator, "按键")

    assert watch.enabled is True
    assert controller.calls == [("pace", "加工 · 等接口"), ("highlight", locator, "按键")]


def test_impl_watch_manual_helpers_are_noop_without_controller():
    watch = ImplWatch(None, RecordingPage())

    watch.pace("加工")
    watch.highlight(object(), "点击")
