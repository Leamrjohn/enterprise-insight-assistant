"""格式校验器 —— 检查答案是否符合基本格式约定"""


def validate_schema(answer: str, evidence_count: int) -> tuple[bool, list[str]]:
    """
    检查答案的格式是否符合基本约定。

    evidence_count: 提供证据的总条数。如果 > 0，答案应有引用标记。
                    如果 == 0，答案应明确说明无法回答。

    返回：(is_valid, rule_violations)
    """
    errors = []

    # 规则1：答案不能为空
    if not answer or not answer.strip():
        errors.append("答案为空")
        return (False, errors)

    # 规则2：如果有证据，答案应该包含引用标记
    if evidence_count > 0:
        if "[来源:" not in answer and "[引用" not in answer:
            errors.append(f"有{evidence_count}条证据，但答案未包含引用标记")

    # 规则3：如果无证据，答案应该明确说明无法回答
    if evidence_count == 0:
        if "无法回答" not in answer and "资料不足" not in answer:
            errors.append("无证据时，答案未明确说明无法回答")

    if not errors:
        return (True, [])
    return (False, errors)
