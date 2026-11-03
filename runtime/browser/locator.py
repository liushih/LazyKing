"""浏览器统一定位器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class LocatorError(Exception):
    pass


class LocatorMatchError(Exception):
    def __init__(self, description: str, count: int, candidates: list[str]):
        self.count = count
        self.candidates = candidates
        super().__init__(f"{description} 命中 {count} 个元素：{candidates}")


@dataclass(frozen=True)
class LocatorSpec:
    kind: str
    value: str
    name: str | None = None
    exact: bool = False
    last: bool = False
    within: str | None = None


_KINDS = ("testid", "role", "text", "placeholder", "css")
_ALLOWED = set(_KINDS) | {"name", "exact", "last", "in"}


def parse_locator(spec: dict) -> LocatorSpec:
    if not isinstance(spec, dict):
        raise LocatorError("定位器必须是映射")
    unknown = sorted(set(spec) - _ALLOWED)
    if unknown:
        raise LocatorError(f"定位器含未知字段：{', '.join(unknown)}")
    kinds = [kind for kind in _KINDS if kind in spec]
    if len(kinds) != 1:
        raise LocatorError(f"定位器必须且只能包含一个类型：{'/'.join(_KINDS)}")
    kind = kinds[0]
    value = spec[kind]
    if not isinstance(value, str) or not value.strip():
        raise LocatorError(f"定位器的 {kind} 必须是非空字符串")

    name = spec.get("name")
    if kind == "role" and (not isinstance(name, str) or not name.strip()):
        raise LocatorError("role 定位必须提供 name")
    if name is not None and not isinstance(name, str):
        raise LocatorError("定位器的 name 必须是字符串")

    exact = spec.get("exact", False)
    if not isinstance(exact, bool):
        raise LocatorError("定位器的 exact 必须是布尔值")
    last = spec.get("last", False)
    if not isinstance(last, bool):
        raise LocatorError("定位器的 last 必须是布尔值")
    within = spec.get("in")
    if within is not None and (not isinstance(within, str) or not within.strip()):
        raise LocatorError("定位器的 in 必须是非空字符串")

    return LocatorSpec(
        kind=kind,
        value=value,
        name=name,
        exact=exact,
        last=last,
        within=within,
    )


def describe_locator(spec: LocatorSpec) -> str:
    prefix = f"in={spec.within} " if spec.within else ""
    if spec.kind == "role":
        return f"{prefix}role={spec.value}[name={spec.name}]"
    return f"{prefix}{spec.kind}={spec.value}"


def _build(scope: Any, spec: LocatorSpec) -> Any:
    if spec.kind == "testid":
        return scope.get_by_test_id(spec.value)
    if spec.kind == "role":
        return scope.get_by_role(spec.value, name=spec.name, exact=spec.exact)
    if spec.kind == "text":
        return scope.get_by_text(spec.value, exact=spec.exact)
    if spec.kind == "placeholder":
        return scope.get_by_placeholder(spec.value, exact=spec.exact)
    return scope.locator(spec.value)


def _candidates(locator: Any, count: int) -> list[str]:
    candidates: list[str] = []
    for index in range(min(count, 5)):
        try:
            text = locator.nth(index).evaluate(
                "el => (el.closest('tr')?.innerText || el.innerText || '').trim()"
            )
        except Exception:
            text = ""
        candidates.append(text)
    return candidates


def find(scope: Any, spec: dict | LocatorSpec, aliases: dict[str, Any]) -> Any:
    parsed = spec if isinstance(spec, LocatorSpec) else parse_locator(spec)
    if parsed.within:
        if parsed.within not in aliases:
            raise LocatorError(f"未定义的定位别名：{parsed.within}")
        scope = aliases[parsed.within]

    locator = _build(scope, parsed)
    count = locator.count()
    if count > 1 and not parsed.last:
        raise LocatorMatchError(describe_locator(parsed), count, _candidates(locator, count))
    return locator.last if parsed.last else locator.first
