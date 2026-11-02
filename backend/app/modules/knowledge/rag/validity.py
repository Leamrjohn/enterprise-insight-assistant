"""Work out from the question which period a document must be valid in.

Code decides this, not the model: a wrong guess here would silently hand the
report a retired rule.  A question with no time reference asks about today.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

BUSINESS_TIMEZONE = timezone(timedelta(hours=8))
_MONTH = r"(\d{1,2}|十[一二]?|[一二三四五六七八九])"
_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
_DAY = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_QUARTER = re.compile(r"(20\d{2})\s*年?\s*(?:第?([一二三四1-4])季度|[Qq]([1-4]))")
_HALF = re.compile(r"(20\d{2})\s*年?\s*(上|下)半年")
_MONTH_OF_YEAR = re.compile(rf"(20\d{{2}})(?:年|-|/)\s*{_MONTH}月?")
_YEAR = re.compile(r"(20\d{2})\s*(?:财年|年度?|版)")
_RELATIVE_YEARS = {"今年": 0, "去年": 1, "前年": 2}
_CURRENT = re.compile(r"现在|目前|当前|现行|最新|如今")
_ANY_VERSION = re.compile(r"旧版|老版|历史版本|历次|修订前|调整前|原规定|以前的")


@dataclass(frozen=True)
class ValidityWindow:
    start: date
    end: date

    def to_parameter(self) -> list[str]:
        return [self.start.isoformat(), self.end.isoformat()]

    @classmethod
    def from_parameter(cls, value: object) -> "ValidityWindow":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("validity window must be a [start, end] pair")
        start, end = date.fromisoformat(value[0]), date.fromisoformat(value[1])
        if start > end:
            raise ValueError("validity window starts after it ends")
        return cls(start, end)


def business_today() -> date:
    """Today on the company's calendar; validity dates are written in this zone."""
    return datetime.now(BUSINESS_TIMEZONE).date()


def _number(token: str) -> int:
    return _CHINESE_NUMBERS[token] if token in _CHINESE_NUMBERS else int(token)


def _months(year: int, first: int, last: int) -> tuple[date, date]:
    return (
        date(year, first, 1),
        date(year, last, calendar.monthrange(year, last)[1]),
    )


def _explicit_periods(question: str, today: date) -> list[tuple[date, date]]:
    periods: list[tuple[date, date]] = []

    def consume(pattern: re.Pattern, build) -> None:
        nonlocal question
        for match in pattern.finditer(question):
            try:
                periods.append(build(match))
            except ValueError:  # 2024年13月 is not a date
                continue
        question = pattern.sub(" ", question)

    def day(match: re.Match) -> tuple[date, date]:
        value = date(int(match[1]), int(match[2]), int(match[3]))
        return value, value

    def quarter(match: re.Match) -> tuple[date, date]:
        index = _number(match[2] or match[3])
        return _months(int(match[1]), index * 3 - 2, index * 3)

    # Most specific first: each pattern removes what it matched.
    consume(_DAY, day)
    consume(_QUARTER, quarter)
    consume(
        _HALF,
        lambda m: _months(int(m[1]), *((1, 6) if m[2] == "上" else (7, 12))),
    )
    consume(
        _MONTH_OF_YEAR,
        lambda m: _months(int(m[1]), _number(m[2]), _number(m[2])),
    )
    consume(_YEAR, lambda m: _months(int(m[1]), 1, 12))
    for word, years_ago in _RELATIVE_YEARS.items():
        if word in question:
            periods.append(_months(today.year - years_ago, 1, 12))
    return periods


def resolve_validity_window(question: str, today: date) -> ValidityWindow:
    """The period to keep documents for, widened rather than guessed when unclear."""
    if _ANY_VERSION.search(question):
        return ValidityWindow(date.min, today)
    periods = _explicit_periods(question, today)
    if not periods:
        return ValidityWindow(today, today)
    start = min(period[0] for period in periods)
    end = max(period[1] for period in periods)
    if _CURRENT.search(question):
        start, end = min(start, today), max(end, today)
    return ValidityWindow(start, end)
