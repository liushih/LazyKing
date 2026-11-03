import pytest

from runtime.browser.locator import (
    LocatorError,
    LocatorMatchError,
    describe_locator,
    find,
    parse_locator,
)


def test_parse_each_kind():
    assert parse_locator({"testid": "save"}).kind == "testid"
    assert parse_locator({"css": "table tbody tr"}).value == "table tbody tr"
    assert parse_locator({"placeholder": "手机号"}).kind == "placeholder"
    role = parse_locator({"role": "button", "name": "搜索", "exact": True})
    assert (role.kind, role.value, role.name, role.exact) == ("role", "button", "搜索", True)
    assert parse_locator({"text": "更多", "last": True}).last is True


def test_parse_requires_role_name():
    with pytest.raises(LocatorError, match="name"):
        parse_locator({"role": "button"})


def test_parse_rejects_two_kinds():
    with pytest.raises(LocatorError, match="只能"):
        parse_locator({"css": "#a", "text": "a"})


def test_describe_locator():
    assert describe_locator(parse_locator({"testid": "save"})) == "testid=save"


def test_find_by_testid_text_role_css(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    assert find(page, {"testid": "save"}, {}).inner_text() == "保存"
    assert find(page, {"text": "WO001"}, {}).inner_text() == "WO001"
    assert find(page, {"css": "[data-testid=dialog]"}, {}).count() == 1
    assert find(page, {"role": "tab", "name": "待发货"}, {}).inner_text() == "待发货"


def test_find_within_alias(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    row = page.locator("table tbody tr").filter(has_text="WO001")
    assert find(page, {"in": "row", "role": "button", "name": "更多"}, {"row": row}).get_attribute("data-row") == "WO001"


def test_find_rejects_multiple_matches_with_candidates(page, fixture_url):
    page.goto(fixture_url + "/index.html")
    with pytest.raises(LocatorMatchError) as exc:
        find(page, {"role": "button", "name": "更多"}, {})
    assert exc.value.count == 2
    assert any("WO001" in text for text in exc.value.candidates)
