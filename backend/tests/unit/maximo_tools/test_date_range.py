import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.maximo_tools.mappers.date_range import (
    _TZ,
    _EPOCH,
    parse_preset,
    parse_explicit,
    resolve,
)

# 固定 now：2026-04-20 12:00:00 台北時間（週一）
_NOW = datetime(2026, 4, 20, 12, 0, 0, tzinfo=_TZ)


class TestParsePresetLast7d:
    def test_from_is_7_days_before_now(self):
        from_ts, to_ts = parse_preset("last_7d", now=_NOW)
        assert from_ts == _NOW - timedelta(days=7)

    def test_to_is_now(self):
        from_ts, to_ts = parse_preset("last_7d", now=_NOW)
        assert to_ts == _NOW

    def test_from_date_value(self):
        from_ts, _ = parse_preset("last_7d", now=_NOW)
        assert from_ts.date().isoformat() == "2026-04-13"


class TestParsePresetLast30d:
    def test_from_is_30_days_before_now(self):
        from_ts, to_ts = parse_preset("last_30d", now=_NOW)
        assert from_ts == _NOW - timedelta(days=30)
        assert to_ts == _NOW

    def test_from_date_value(self):
        from_ts, _ = parse_preset("last_30d", now=_NOW)
        assert from_ts.date().isoformat() == "2026-03-21"


class TestParsePresetLast90d:
    def test_from_is_90_days_before_now(self):
        from_ts, to_ts = parse_preset("last_90d", now=_NOW)
        assert from_ts == _NOW - timedelta(days=90)
        assert to_ts == _NOW

    def test_from_date_value(self):
        from_ts, _ = parse_preset("last_90d", now=_NOW)
        assert from_ts.date().isoformat() == "2026-01-20"


class TestParsePresetPrevWeek:
    def test_monday_to_sunday(self):
        # _NOW = 2026-04-20（週一，weekday=0）
        # monday = 04-20 - timedelta(0+7) = 04-13（週一）
        # sunday = 04-13 + 6 = 04-19（週日）
        from_ts, to_ts = parse_preset("prev_week", now=_NOW)
        assert from_ts == datetime(2026, 4, 13, 0, 0, 0, tzinfo=_TZ)
        assert to_ts == datetime(2026, 4, 19, 23, 59, 59, 999999, tzinfo=_TZ)

    def test_from_is_monday(self):
        from_ts, _ = parse_preset("prev_week", now=_NOW)
        assert from_ts.weekday() == 0  # Monday

    def test_to_is_sunday(self):
        _, to_ts = parse_preset("prev_week", now=_NOW)
        assert to_ts.weekday() == 6  # Sunday

    def test_span_is_7_days(self):
        from_ts, to_ts = parse_preset("prev_week", now=_NOW)
        # from 00:00:00 → to 23:59:59，不足整 7 天，但日期差是 6
        assert (to_ts.date() - from_ts.date()).days == 6

    def test_mid_week_now(self):
        # now = 2026-04-22（週三，weekday=2）
        # monday = 04-22 - timedelta(2+7) = 04-13（週一）
        # sunday = 04-13 + 6 = 04-19（週日）
        mid_week = datetime(2026, 4, 22, 9, 0, 0, tzinfo=_TZ)
        from_ts, to_ts = parse_preset("prev_week", now=mid_week)
        assert from_ts.date().isoformat() == "2026-04-13"
        assert to_ts.date().isoformat() == "2026-04-19"


class TestParsePresetPrevMonth:
    def test_april_20_returns_march(self):
        from_ts, to_ts = parse_preset("prev_month", now=_NOW)
        assert from_ts == datetime(2026, 3, 1, 0, 0, 0, tzinfo=_TZ)
        assert to_ts == datetime(2026, 3, 31, 23, 59, 59, 999999, tzinfo=_TZ)

    def test_march_1_returns_february(self):
        # 從月初執行：2026-03-01 → prev_month = 2/1–2/28
        mar1 = datetime(2026, 3, 1, 8, 0, 0, tzinfo=_TZ)
        from_ts, to_ts = parse_preset("prev_month", now=mar1)
        assert from_ts.date().isoformat() == "2026-02-01"
        assert to_ts.date().isoformat() == "2026-02-28"

    def test_january_returns_december_prev_year(self):
        jan15 = datetime(2026, 1, 15, 0, 0, 0, tzinfo=_TZ)
        from_ts, to_ts = parse_preset("prev_month", now=jan15)
        assert from_ts.date().isoformat() == "2025-12-01"
        assert to_ts.date().isoformat() == "2025-12-31"

    def test_not_last_30d(self):
        # prev_month 不等於 last_30d：語意不同
        pm_from, _ = parse_preset("prev_month", now=_NOW)
        l30_from, _ = parse_preset("last_30d", now=_NOW)
        assert pm_from != l30_from


class TestParsePresetThisMonth:
    def test_from_is_first_of_month(self):
        from_ts, to_ts = parse_preset("this_month", now=_NOW)
        assert from_ts == datetime(2026, 4, 1, 0, 0, 0, tzinfo=_TZ)
        assert to_ts == _NOW

    def test_to_is_now(self):
        _, to_ts = parse_preset("this_month", now=_NOW)
        assert to_ts == _NOW


class TestParsePresetAll:
    def test_from_is_epoch(self):
        from_ts, _ = parse_preset("all", now=_NOW)
        assert from_ts == _EPOCH

    def test_to_is_now(self):
        _, to_ts = parse_preset("all", now=_NOW)
        assert to_ts == _NOW

    def test_epoch_year(self):
        from_ts, _ = parse_preset("all", now=_NOW)
        assert from_ts.year == 1970


class TestParsePresetUnknown:
    def test_bad_preset_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown date_range preset"):
            parse_preset("bad")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_preset("")

    def test_last_1d_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_preset("last_1d")


class TestParseExplicit:
    def test_valid_range(self):
        from_ts, to_ts = parse_explicit("2026-01-01", "2026-03-15")
        assert from_ts == datetime(2026, 1, 1, 0, 0, 0, tzinfo=_TZ)
        assert to_ts == datetime(2026, 3, 15, 23, 59, 59, 999999, tzinfo=_TZ)

    def test_same_day_is_valid(self):
        from_ts, to_ts = parse_explicit("2026-04-20", "2026-04-20")
        assert from_ts.date() == to_ts.date()
        assert from_ts.hour == 0
        assert to_ts.hour == 23

    def test_reversed_range_raises_value_error(self):
        with pytest.raises(ValueError, match="to_date"):
            parse_explicit("2026-03-15", "2026-01-01")

    def test_invalid_iso_format_raises(self):
        # "2026/01/01" 不是合法 ISO 8601，date.fromisoformat 應 raise ValueError
        with pytest.raises(ValueError):
            parse_explicit("2026/01/01", "2026-03-15")

    def test_from_is_start_of_day(self):
        from_ts, _ = parse_explicit("2026-06-01", "2026-06-30")
        assert (from_ts.hour, from_ts.minute, from_ts.second) == (0, 0, 0)

    def test_to_is_end_of_day(self):
        _, to_ts = parse_explicit("2026-06-01", "2026-06-30")
        assert (to_ts.hour, to_ts.minute, to_ts.second, to_ts.microsecond) == (23, 59, 59, 999999)

    def test_timezone_is_taipei(self):
        from_ts, to_ts = parse_explicit("2026-01-01", "2026-12-31")
        assert from_ts.tzinfo == _TZ
        assert to_ts.tzinfo == _TZ


class TestResolve:
    def test_with_from_and_to_uses_explicit(self):
        from_ts, to_ts = resolve(from_date="2026-01-01", to_date="2026-03-15")
        assert from_ts == datetime(2026, 1, 1, 0, 0, 0, tzinfo=_TZ)
        assert to_ts == datetime(2026, 3, 15, 23, 59, 59, 999999, tzinfo=_TZ)

    def test_default_preset_is_last_30d(self):
        from_ts, to_ts = resolve(now=_NOW)
        assert from_ts == _NOW - timedelta(days=30)
        assert to_ts == _NOW

    def test_explicit_overrides_preset(self):
        # 即使 date_range 設 "last_7d"，有 from_date/to_date 時走 explicit
        from_ts, _ = resolve(
            date_range="last_7d",
            from_date="2026-01-01",
            to_date="2026-01-31",
        )
        assert from_ts.date().isoformat() == "2026-01-01"

    def test_only_from_date_falls_back_to_preset(self):
        # 只有 from_date 沒有 to_date → 仍走 preset
        from_ts, to_ts = resolve(date_range="last_7d", from_date="2026-01-01", now=_NOW)
        assert from_ts == _NOW - timedelta(days=7)

    def test_custom_preset(self):
        from_ts, _ = resolve(date_range="this_month", now=_NOW)
        assert from_ts == datetime(2026, 4, 1, 0, 0, 0, tzinfo=_TZ)
