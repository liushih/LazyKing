"""观看模式：页面悬浮控制条与可调慢放。"""

from __future__ import annotations

import time
from typing import Any, Callable

SPEEDS_MS = (200, 500, 800, 1500, 2500)
DEFAULT_SPEED_INDEX = 3
HIGHLIGHT_HOLD_SECONDS = 0.9
POLL_INTERVAL = 0.1
_MAX_DRAIN_FAILURES = 20

_INSTALL_JS = """
() => {
  if (window.__dataToolsWatch) return;
  const host = document.createElement('div');
  host.id = '__data-tools-watch';
  host.style.cssText = 'all:initial;position:fixed;top:12px;right:12px;z-index:2147483647;';
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      .bar{font:13px/1.4 "Microsoft YaHei",system-ui,sans-serif;background:rgba(23,23,28,.92);color:#fff;
           border-radius:8px;padding:8px 10px;box-shadow:0 6px 20px rgba(0,0,0,.35);
           display:flex;flex-direction:column;gap:6px;min-width:230px;user-select:none}
      .row{display:flex;gap:6px;align-items:center;flex-wrap:nowrap}
      .label{font-weight:600;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .speed{opacity:.75;margin-left:auto;white-space:nowrap}
      button{font:inherit;color:#fff;background:#3b3b46;border:0;border-radius:6px;padding:4px 10px;cursor:pointer;white-space:nowrap}
      button:hover{background:#50505e}
      button.primary{background:#2f6fed}
      button.primary:hover{background:#3f7ffd}
    </style>
    <div class="bar">
      <div class="row"><span class="label">准备中…</span><span class="speed"></span></div>
      <div class="row">
        <button type="button" data-act="toggle" class="primary">暂停</button>
        <button type="button" data-act="slower">慢一点</button>
        <button type="button" data-act="faster">快一点</button>
      </div>
    </div>`;

  const api = {
    events: [],
    set(state) {
      state = state || {};
      root.querySelector('.label').textContent = state.label || '';
      root.querySelector('.speed').textContent = state.speed || '';
      root.querySelector('[data-act=toggle]').textContent = state.paused ? '继续' : '暂停';
    },
    hide() { host.style.display = 'none'; },
    show() { host.style.display = ''; },
  };

  // 控制条写在宿主页面里：点它不能触发页面的「点外部关闭」实现，也不能把焦点从
  // 已展开的下拉框上抢走。window 捕获阶段比 document 上的监听更早，先在这里截住。
  const pathOf = (event) => (typeof event.composedPath === 'function' ? event.composedPath() : []);
  const fromBar = (event) => pathOf(event).indexOf(host) !== -1;
  const guard = (event) => {
    if (!fromBar(event)) return;
    event.stopImmediatePropagation();
    if (event.type === 'pointerdown' || event.type === 'mousedown') {
      event.preventDefault();
    }
    if (event.type === 'click') {
      const button = pathOf(event).find((node) => node && node.dataset && node.dataset.act);
      if (button) api.events.push(button.dataset.act);
    }
  };
  ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click'].forEach((type) =>
    window.addEventListener(type, guard, true)
  );

  window.__dataToolsWatch = api;
  const mount = () => (document.body || document.documentElement).appendChild(host);
  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount, { once: true });
}
"""

_DRAIN_JS = """
() => {
  const watch = window.__dataToolsWatch;
  if (!watch) return [];
  const events = watch.events.slice();
  watch.events.length = 0;
  return events;
}
"""

_SET_JS = """
(state) => {
  const watch = window.__dataToolsWatch;
  if (watch) watch.set(state);
}
"""

_HIDE_JS = """
() => {
  const watch = window.__dataToolsWatch;
  if (watch) watch.hide();
}
"""

_SHOW_JS = """
() => {
  const watch = window.__dataToolsWatch;
  if (watch) watch.show();
}
"""

_SUMMARY_JS = """
(el) => {
  const oneLine = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const text = oneLine(el.innerText);
  const placeholder = oneLine(el.getAttribute && el.getAttribute('placeholder'));
  const testid = oneLine(el.getAttribute && el.getAttribute('data-testid'));
  const id = oneLine(el.id);
  const tag = el.tagName ? el.tagName.toLowerCase() : '';
  return (text || placeholder || testid || id || tag).slice(0, 16);
}
"""

_HIGHLIGHT_JS = """
(state) => {
  const old = document.getElementById('__data-tools-highlight');
  if (old) old.remove();
  const host = document.createElement('div');
  host.id = '__data-tools-highlight';
  host.style.cssText = 'all:initial;position:fixed;left:0;top:0;right:0;bottom:0;' +
    'z-index:2147483646;pointer-events:none;';
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <style>
      .box{position:fixed;border:2px solid #ff5a1f;border-radius:4px;pointer-events:none;
           box-shadow:0 0 0 2px rgba(255,90,31,.22),0 0 14px rgba(255,90,31,.45);}
      .label{position:fixed;font:600 13px/1.3 "Microsoft YaHei",system-ui,sans-serif;color:#fff;
             background:#ff5a1f;border-radius:5px;padding:3px 8px;white-space:nowrap;
             max-width:320px;overflow:hidden;text-overflow:ellipsis;pointer-events:none;
             box-shadow:0 3px 10px rgba(0,0,0,.28);}
    </style>
    <div class="box"></div><div class="label"></div>`;
  const box = root.querySelector('.box');
  const label = root.querySelector('.label');
  const pad = 3;
  const left = Math.max(0, state.x - pad);
  box.style.left = left + 'px';
  box.style.top = Math.max(0, state.y - pad) + 'px';
  box.style.width = (state.width + pad * 2) + 'px';
  box.style.height = (state.height + pad * 2) + 'px';
  label.textContent = state.text;
  label.style.left = left + 'px';
  const above = state.y - pad - 26;
  label.style.top = (above >= 4 ? above : state.y + state.height + pad + 4) + 'px';
  (document.body || document.documentElement).appendChild(host);
  setTimeout(() => { if (host.parentNode) host.parentNode.removeChild(host); }, state.hold_ms);
  return true;
}
"""


class WatchController:
    """观看模式的速度与暂停状态；只在步骤边界生效。"""

    def __init__(
        self,
        page: Any,
        *,
        speeds_ms: tuple[int, ...] = SPEEDS_MS,
        speed_index: int = DEFAULT_SPEED_INDEX,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = POLL_INTERVAL,
    ) -> None:
        self.page = page
        self.speeds_ms = tuple(speeds_ms)
        self.speed_index = max(0, min(speed_index, len(self.speeds_ms) - 1))
        self.paused = False
        self.label = "准备中…"
        self.poll_interval = poll_interval
        self._sleep = sleep
        self._drain_failures = 0

    @property
    def delay_ms(self) -> int:
        return self.speeds_ms[self.speed_index]

    @property
    def speed_text(self) -> str:
        return f"{self.delay_ms / 1000:.1f}s"

    @property
    def lead_seconds(self) -> float:
        """动作前留给观众看清高亮的提前量：不超过档速的一半，最快档也不省到看不见。"""
        return max(0.1, min(0.5, self.delay_ms / 2000))

    def status_text(self) -> str:
        return f"已暂停 · {self.label}" if self.paused else self.label

    def attach(self) -> None:
        """注入控制条；之后每个新页面加载都会自动重建。"""
        try:
            self.page.context.add_init_script(f"({_INSTALL_JS})()")
        except Exception:
            pass
        self._evaluate(_INSTALL_JS)
        self._refresh()

    def pace(self, label: str) -> None:
        """在步骤开始前按当前速度停顿；暂停时一直等到用户点继续。"""
        self.label = label
        self._refresh()
        self._apply(self._drain())
        if not self.paused:
            self._sleep(self.delay_ms / 1000)
            return
        while self.paused and not self._closed():
            self._refresh()
            self._sleep(self.poll_interval)
            self._apply(self._drain())
        self._refresh()

    def highlight(self, locator: Any, verb: str) -> None:
        """动作前在页面上框出目标，并停顿一小会儿让观众看清。

        取不到元素位置、页面已关闭等情况下静默跳过，只是没有高亮，不能影响流程本身。
        """
        try:
            locator.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass
        try:
            box = locator.bounding_box()
            if box is None:
                return
            summary = str(locator.evaluate(_SUMMARY_JS) or "")
            text = f"{verb} · {summary}" if summary else verb
            self._evaluate(
                _HIGHLIGHT_JS,
                {
                    "x": float(box["x"]),
                    "y": float(box["y"]),
                    "width": float(box["width"]),
                    "height": float(box["height"]),
                    "text": text,
                    "hold_ms": int((self.lead_seconds + HIGHLIGHT_HOLD_SECONDS) * 1000),
                },
            )
        except Exception:
            return
        self._sleep(self.lead_seconds)

    def hide(self) -> None:
        self._evaluate(_HIDE_JS)

    def show(self) -> None:
        self._evaluate(_SHOW_JS)

    def _apply(self, events: list[str]) -> None:
        for event in events:
            if event == "toggle":
                self.paused = not self.paused
            elif event == "slower":
                self.speed_index = min(self.speed_index + 1, len(self.speeds_ms) - 1)
            elif event == "faster":
                self.speed_index = max(self.speed_index - 1, 0)

    def _drain(self) -> list[str]:
        try:
            events = self.page.evaluate(_DRAIN_JS)
            self._drain_failures = 0
        except Exception:
            self._drain_failures += 1
            # 页面异常时不能让暂停把流程永久卡死；连续失败就自动恢复。
            if self._drain_failures >= _MAX_DRAIN_FAILURES:
                self.paused = False
            return []
        return [str(event) for event in events or []]

    def _refresh(self) -> None:
        self._evaluate(
            _SET_JS,
            {"label": self.status_text(), "speed": self.speed_text, "paused": self.paused},
        )

    def _evaluate(self, script: str, arg: Any = None) -> Any:
        try:
            if arg is None:
                return self.page.evaluate(script)
            return self.page.evaluate(script, arg)
        except Exception:
            return None

    def _closed(self) -> bool:
        try:
            return bool(self.page.is_closed())
        except Exception:
            return False
