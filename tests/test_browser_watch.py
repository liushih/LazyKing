import pytest

from runtime.browser import watch as watch_mod
from runtime.browser.watch import WatchController


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


def test_pace_waits_one_action_interval():
    page = FakePage()
    sleeps = []
    controller = WatchController(page, sleep=sleeps.append)

    controller.pace("步骤 1/3：打开")

    assert sleeps == [0.8]
    assert controller.delay_ms == 800
    assert controller.speed_text == "0.8s"
    assert page.states()[-1] == {"label": "步骤 1/3：打开", "speed": "0.8s", "paused": False}


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
    assert sleeps == [1.5, 2.5, 0.2]


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

    assert controller.delay_ms == 1500
    assert sleeps == [1.5]


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
