from datetime import datetime, date, timedelta
from typing import Literal, Final
from zoneinfo import ZoneInfo

DateRangePreset = Literal[
    "last_7d", "last_30d", "last_90d",
    "prev_week", "prev_month", "this_month",
    "all",
]

_TZ: Final[ZoneInfo] = ZoneInfo("Asia/Taipei")
_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=_TZ)


def parse_preset(preset: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """把 preset 解析成 (from_ts, to_ts)。now 可 inject for testing。"""
    now = now or datetime.now(_TZ)
    today = now.date()

    match preset:
        case "last_7d":
            return (now - timedelta(days=7), now)
        case "last_30d":
            return (now - timedelta(days=30), now)
        case "last_90d":
            return (now - timedelta(days=90), now)
        case "prev_week":
            # 上週一 00:00 到 上週日 23:59:59.999999
            monday = today - timedelta(days=today.weekday() + 7)
            sunday = monday + timedelta(days=6)
            return (_start_of_day(monday), _end_of_day(sunday))
        case "prev_month":
            # 上個完整月份（4/20 執行 → 3/1–3/31）
            first_of_this_month = today.replace(day=1)
            last_of_prev = first_of_this_month - timedelta(days=1)
            first_of_prev = last_of_prev.replace(day=1)
            return (_start_of_day(first_of_prev), _end_of_day(last_of_prev))
        case "this_month":
            # 本月 1 號 00:00 到 today now
            first_of_month = today.replace(day=1)
            return (_start_of_day(first_of_month), now)
        case "all":
            return (_EPOCH, now)
        case _:
            raise ValueError(f"Unknown date_range preset: {preset!r}")


def parse_explicit(from_date: str, to_date: str) -> tuple[datetime, datetime]:
    """把 ISO 8601 date 字串解析成 tuple（from 00:00:00 → to 23:59:59.999999）。"""
    from_d = date.fromisoformat(from_date)
    to_d = date.fromisoformat(to_date)
    if to_d < from_d:
        raise ValueError(f"to_date {to_date!r} is before from_date {from_date!r}")
    return (_start_of_day(from_d), _end_of_day(to_d))


def resolve(
    date_range: str = "last_30d",
    from_date: str | None = None,
    to_date: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """統一入口：若 from_date + to_date 都提供 → explicit；否則走 preset。"""
    if from_date and to_date:
        return parse_explicit(from_date, to_date)
    return parse_preset(date_range, now)


def _start_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_TZ)


def _end_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=_TZ)
