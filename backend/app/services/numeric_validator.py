"""数字校验器 —— 防止答案把接近但不同的 SQL 数值说成事实。"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?%?")


def _numbers_from_value(value: object) -> list[Decimal]:
    if isinstance(value, dict):
        return [
            number for item in value.values() for number in _numbers_from_value(item)
        ]
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _numbers_from_value(item)]
    if value is None or isinstance(value, bool):
        return []
    return [Decimal(match) for match in re.findall(r"-?\d+(?:\.\d+)?", str(value))]


def _display_matches_source(
    answer_number: Decimal,
    *,
    has_percent_sign: bool,
    source_numbers: list[Decimal],
) -> bool:
    """Allow only exact values or the rounding implied by the displayed precision."""
    exponent = answer_number.as_tuple().exponent
    if not isinstance(exponent, int):
        return False
    precision = Decimal(1).scaleb(exponent)
    candidates = list(source_numbers)
    if has_percent_sign:
        candidates.extend(
            number * 100 for number in source_numbers if Decimal("-1") <= number <= 1
        )
    for candidate in candidates:
        if candidate == answer_number:
            return True
        try:
            if candidate.quantize(precision, rounding=ROUND_HALF_UP) == answer_number:
                return True
        except InvalidOperation:
            continue
    return False


def validate_numbers(answer: str, data_result: dict | None) -> tuple[bool, list[str]]:
    """Validate displayed values against SQL output without a percentage tolerance."""
    answer_without_citations = re.sub(r"\[(?:来源|引用)[：:\s]*\d+\]", "", answer)
    answer_numbers: list[tuple[Decimal, bool]] = []
    for matched in _NUMBER_PATTERN.findall(answer_without_citations):
        try:
            answer_numbers.append(
                (Decimal(matched.removesuffix("%")), matched.endswith("%"))
            )
        except InvalidOperation:
            continue
    if not answer_numbers:
        return True, []

    source_numbers = [
        number
        for evidence in (data_result or {}).get("evidence", [])
        for number in _numbers_from_value(evidence.get("rows", []))
    ]
    if not source_numbers:
        return False, ["数据源中没有数值，无法校验答案中的数字"]

    mismatches = [
        f"答案提及 {answer_number}{'%' if has_percent else ''}，但数据源中未找到精确或同精度舍入匹配值"
        for answer_number, has_percent in answer_numbers
        if not _display_matches_source(
            answer_number,
            has_percent_sign=has_percent,
            source_numbers=source_numbers,
        )
    ]
    return not mismatches, mismatches
