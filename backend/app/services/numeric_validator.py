"""数字校验器 —— 检查答案中的数字是否与数据源一致"""

import re


def validate_numbers(answer: str, data_result: dict | None) -> tuple[bool, list[str]]:
    """
    校验答案中的数字是否能在 SQL 结果中找到匹配。

    返回：(is_valid, mismatch_descriptions)
    """
    # 1. 从答案中提取数字
    pattern = r"\d+(?:\.\d+)?%?"
    matches = re.findall(pattern, answer)
    answer_numbers = []
    for m in matches:
        clean = m.replace("%", "")
        try:
            answer_numbers.append(float(clean))
        except ValueError:
            continue

    if not answer_numbers:
        return (True, [])

    # 2. 从 SQL 结果中提取数字（多层嵌套安全提取）
    sql_numbers = []
    if data_result:
        evidence = data_result.get("evidence", [])
        if evidence:
            rows = evidence[0].get("rows", [])
            for row in rows:
                if len(row) >= 2:
                    try:
                        sql_numbers.append(abs(float(row[1])))
                    except (ValueError, TypeError):
                        continue

    # 3. 如果没有 SQL 数据，答案中的所有数字都不可靠
    if not sql_numbers:
        return (False, ["数据源中没有数值，无法校验答案中的数字"])

    # 4. 逐个对比（容差 ≤ 10%）
    mismatches = []
    for ans_val in answer_numbers:
        found = False
        for sql_val in sql_numbers:
            denominator = abs(sql_val) if sql_val != 0 else 1e-9
            if abs(ans_val - sql_val) / denominator <= 0.1:
                found = True
                break
        if not found:
            mismatches.append(f"答案提及 {ans_val}，但数据源中未找到匹配值")

    if not mismatches:
        return (True, [])
    return (False, mismatches)
