"""What code can see in a question before any model runs (B2c: recorded, not used).

These are word-level observations, not decisions. Plan rules (B2d) interpret them,
first in shadow mode, so a wrong word list costs nothing until a rule is enforced.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from app.modules.knowledge.rag.validity import explicit_periods

FACTS_VERSION = "facts/1"

# Precision over coverage: a missing word only leaves the Planner unchecked, a wrong
# one makes a rule overrule a correct plan. Matching is by substring, so no bare
# "比" (it hits 比例), no "因素" (factors are not a why-question), no "根据" (根据销售数据).
QUANTITY_WORDS: tuple[str, ...] = (
    "多少",
    "比例",
    "占比",
    "百分比",
    "合计",
    "总额",
    "平均",
    "几个",
    "几天",
)
DOCUMENT_WORDS: tuple[str, ...] = (
    "资料",
    "文档",
    "文件",
    "简报",
    "风险提示",
    "纪要",
    "手册",
    "制度",
)
COMPARISON_WORDS: tuple[str, ...] = (
    "比较",
    "对比",
    "相比",
    "相较",
    "环比",
    "同比",
    "差异",
    "比上月",
    "比去年",
)
CAUSAL_WORDS: tuple[str, ...] = ("为什么", "为何", "原因", "导致", "归因", "怎么会")
RELATIVE_PERIOD_WORDS: tuple[str, ...] = (
    "本月",
    "当月",
    "上月",
    "上个月",
    "本季度",
    "上季度",
    "今年",
    "本年",
    "去年",
    "前年",
    "本周",
    "上周",
    "今天",
    "昨天",
    "最近",
    "近期",
    "近一年",
    "近半年",
)

# "2025年7月与8月": the second month inherits the year stated for the first.
_FOLLOWING_MONTH = re.compile(
    r"(20\d{2})年(\d{1,2})月(?:与|和|及|以及|、|至|到|-)(\d{1,2})月"
)


@dataclass(frozen=True)
class QuestionFacts:
    periods: tuple[tuple[date, date], ...]
    period_is_relative: bool
    asks_quantity: bool
    wants_document: bool
    is_comparison: bool
    is_causal: bool

    def event_details(self) -> dict:
        """Dates and flags only; the question text never enters the event."""
        return {
            "version": FACTS_VERSION,
            "periods": [
                [start.isoformat(), end.isoformat()] for start, end in self.periods
            ],
            "period_is_relative": self.period_is_relative,
            "asks_quantity": self.asks_quantity,
            "wants_document": self.wants_document,
            "is_comparison": self.is_comparison,
            "is_causal": self.is_causal,
        }


def _mentions(question: str, words: tuple[str, ...]) -> bool:
    return any(word in question for word in words)


def _month(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def extract_question_facts(question: str, today: date) -> QuestionFacts:
    periods = set(explicit_periods(question, today))
    for match in _FOLLOWING_MONTH.finditer(question):
        try:
            periods.add(_month(int(match[1]), int(match[3])))
        except ValueError:  # 2025年7月与13月 is not a month
            continue
    return QuestionFacts(
        periods=tuple(sorted(periods)),
        period_is_relative=_mentions(question, RELATIVE_PERIOD_WORDS),
        asks_quantity=_mentions(question, QUANTITY_WORDS),
        wants_document=_mentions(question, DOCUMENT_WORDS),
        is_comparison=_mentions(question, COMPARISON_WORDS),
        is_causal=_mentions(question, CAUSAL_WORDS),
    )
