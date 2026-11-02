from datetime import datetime, timedelta, timezone

from scripts.update import (
    Version,
    cache_is_fresh,
    is_newer,
    parse_version,
    read_cache,
    write_cache,
)


def test_parse_version_accepts_v_prefix():
    assert parse_version("v1.4.0") == Version(1, 4, 0)


def test_is_newer_compares_numerically():
    assert is_newer("1.9.0", "1.10.0") is True
    assert is_newer("1.10.0", "1.9.0") is False


def test_cache_round_trip(tmp_path):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    write_cache(tmp_path, "1.5.0", "abc1234", now)
    cache = read_cache(tmp_path)
    assert cache["latest_version"] == "1.5.0"
    assert cache_is_fresh(cache, now + timedelta(hours=1), 24) is True
    assert cache_is_fresh(cache, now + timedelta(hours=25), 24) is False