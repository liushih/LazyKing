"""页面显示检查：字段完整性与截断扫描。"""

from __future__ import annotations

import time
from typing import Any

from .apiwatch import ApiWatch
from .locator import find

MAX_PROBLEMS = 50
MAX_TEXT_ELEMENTS = 5000
POLL_INTERVAL = 0.1

DISPLAY_JS = r"""
(container, args) => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'CANVAS',
                        'IMG', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BR', 'HR']);
  const EPS = 1;
  const MAX_PROBLEMS = 50;
  const MAX_TEXT_ELEMENTS = 5000;
  const problems = [];
  const reported = new Set();

  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const textOf = (el) => (el.innerText || '').replace(/\s+/g, ' ').trim();

  const classOf = (el) => (typeof el.className === 'string' ? el.className.trim() : '');

  const describe = (el) => ({
    tag: el.tagName ? el.tagName.toLowerCase() : null,
    testid: el.getAttribute ? el.getAttribute('data-testid') : null,
    class: classOf(el) || null,
    text: textOf(el).slice(0, 80) || null,
  });

  const add = (el, problem) => {
    if (problems.length >= MAX_PROBLEMS) return;
    const full = {kind: null, field: null, text: null, tag: null, testid: null, class: null, reason: ''};
    Object.assign(full, describe(el), problem);
    problems.push(full);
    if (el) reported.add(el);
  };

  const candidates = [];
  let textElements = 0;
  const nodes = [container];
  for (const el of container.querySelectorAll('*')) nodes.push(el);
  for (const el of nodes) {
    if (SKIP.has(el.tagName)) continue;
    if (!visible(el)) continue;
    let hasText = false;
    for (const node of el.childNodes) {
      if (node.nodeType === 3 && node.textContent.trim()) { hasText = true; break; }
    }
    if (!hasText) continue;
    textElements += 1;
    if (candidates.length < MAX_TEXT_ELEMENTS) candidates.push(el);
  }

  const domText = (container.textContent || '').replace(/\s+/g, ' ').trim();
  const findTextEl = (needle) => {
    const matches = candidates.filter((el) => textOf(el).includes(needle));
    if (!matches.length) return null;
    return matches.find((el) => !matches.some((other) => other !== el && el.contains(other))) || matches[0];
  };

  const ancestorDesc = (el) => {
    const tag = el.tagName.toLowerCase();
    const cls = classOf(el);
    return cls ? tag + '.' + cls.split(/\s+/).join('.') : tag;
  };

  const clipped = (el) => {
    const reasons = [];
    const cs = getComputedStyle(el);
    if ((cs.overflowX === 'hidden' || cs.overflowX === 'clip') && el.scrollWidth > el.clientWidth + EPS) {
      reasons.push('scrollWidth ' + el.scrollWidth + ' > clientWidth ' + el.clientWidth);
    }
    if ((cs.overflowY === 'hidden' || cs.overflowY === 'clip') && el.scrollHeight > el.clientHeight + EPS) {
      reasons.push('scrollHeight ' + el.scrollHeight + ' > clientHeight ' + el.clientHeight);
    }
    const clamp = cs.webkitLineClamp;
    if (clamp && clamp !== 'none' && el.scrollHeight > el.clientHeight + EPS) {
      reasons.push('line-clamp ' + clamp + ' 内容超出');
    }
    let ancestor = el.parentElement;
    while (ancestor) {
      const acs = getComputedStyle(ancestor);
      const clipX = acs.overflowX === 'hidden' || acs.overflowX === 'clip';
      const clipY = acs.overflowY === 'hidden' || acs.overflowY === 'clip';
      if (clipX || clipY) {
        const rect = el.getBoundingClientRect();
        const box = ancestor.getBoundingClientRect();
        const beyond = (clipX && (rect.left < box.left - EPS || rect.right > box.right + EPS)) ||
                       (clipY && (rect.top < box.top - EPS || rect.bottom > box.bottom + EPS));
        if (beyond) {
          reasons.push('被祖先 ' + ancestorDesc(ancestor) + ' 裁切');
          break;
        }
      }
      if (ancestor === container) break;
      ancestor = ancestor.parentElement;
    }
    return reasons;
  };

  const allowed = (el) => {
    const text = textOf(el);
    return (args.allow_truncate || []).some((rule) => {
      if (typeof rule === 'string') return text.includes(rule);
      if (rule && rule.css) {
        try { return el.matches(rule.css); } catch (err) { return false; }
      }
      return false;
    });
  };

  const checkField = (raw) => {
    const isObject = raw !== null && typeof raw === 'object';
    const label = isObject ? raw.label : raw;
    const value = isObject ? raw.value : null;
    const labelEl = findTextEl(String(label));
    if (!labelEl) {
      add(container, {
        kind: 'missing_field',
        field: String(label),
        reason: domText.includes(String(label)) ? '存在但不可见' : '容器内未找到该文字',
      });
    } else {
      const reasons = clipped(labelEl);
      if (reasons.length && !allowed(labelEl)) {
        add(labelEl, {kind: 'truncated', field: String(label), reason: reasons.join('；')});
      }
    }
    if (value === null || value === undefined || value === '' || value === false) return;
    const valueText = String(value);
    const valueEl = findTextEl(valueText);
    if (!valueEl) {
      add(container, {
        kind: 'empty_value',
        field: String(label),
        text: valueText.slice(0, 80),
        reason: domText.includes(valueText) ? '期望值存在但不可见' : '标签可见，期望值未显示',
      });
      return;
    }
    const reasons = clipped(valueEl);
    if (reasons.length && !allowed(labelEl) && !allowed(valueEl)) {
      add(valueEl, {kind: 'truncated', field: String(label), reason: reasons.join('；')});
    }
  };

  for (const field of args.fields || []) checkField(field);

  if (args.scan !== false) {
    for (const el of candidates) {
      if (reported.has(el) || allowed(el)) continue;
      const reasons = clipped(el);
      if (reasons.length) add(el, {kind: 'truncated', field: null, reason: reasons.join('；')});
      if (problems.length >= MAX_PROBLEMS) break;
    }
  }

  return {problems, scan_limited: textElements > MAX_TEXT_ELEMENTS, text_elements: textElements};
}
"""


def _summarize(problems: list[dict], scan_limited: bool) -> str:
    missing = [str(p["field"]) for p in problems if p["kind"] == "missing_field" and p.get("field")]
    empty = [str(p["field"]) for p in problems if p["kind"] == "empty_value" and p.get("field")]
    truncated = [p for p in problems if p["kind"] == "truncated"]
    parts: list[str] = []
    if missing:
        parts.append("缺少字段 " + "、".join(missing[:3]) + ("…" if len(missing) > 3 else ""))
    if empty:
        parts.append("值为空 " + "、".join(empty[:3]) + ("…" if len(empty) > 3 else ""))
    if truncated:
        names = [str(p.get("field") or p.get("text") or p.get("tag") or "元素") for p in truncated]
        parts.append(f"{len(truncated)} 处内容被裁切（" + "、".join(names[:3]) + ("…" if len(names) > 3 else "") + "）")
    if scan_limited:
        parts.append("扫描已达上限")
    if not parts:
        parts.append(str(problems[0].get("reason") or "发现问题"))
    return "显示检查未通过：" + "；".join(parts)


def check_display(
    page: Any,
    spec: dict,
    aliases: dict[str, Any],
    timeout_ms: int,
    watch: ApiWatch | None = None,
) -> None:
    from .flow import StepAssertion

    locator = find(page, spec["locator"], aliases)
    args = {
        "fields": spec.get("fields") or [],
        "scan": spec.get("scan", True),
        "allow_truncate": spec.get("allow_truncate") or [],
    }
    deadline = time.monotonic() + timeout_ms / 1000
    problems: list[dict] | None = None
    scan_limited = False

    while True:
        try:
            if locator.is_visible():
                result = locator.evaluate(DISPLAY_JS, args)
                if result is not None:
                    problems = result.get("problems") or []
                    scan_limited = bool(result.get("scan_limited"))
                    if not problems:
                        return
        except Exception as exc:
            # 浏览器被关闭时立即上抛；页面尚未渲染完的普通异常继续轮询。
            if type(exc).__name__ == "TargetClosedError":
                raise
        if watch is not None:
            watch.check()
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_INTERVAL)

    if not problems:
        problems = [{
            "kind": "missing_field",
            "field": None,
            "text": None,
            "tag": None,
            "testid": None,
            "class": None,
            "reason": "容器未出现或不可见",
        }]
    raise StepAssertion(
        _summarize(problems, scan_limited),
        "字段齐全且内容未被裁切",
        f"{len(problems)} 个问题",
        {"display_problems": problems, "scan_limited": scan_limited},
    )
