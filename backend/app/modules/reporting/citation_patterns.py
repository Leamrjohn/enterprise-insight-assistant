"""Keep numeric exclusion and citation authorization on the same syntax."""

import re

CITATION_PATTERN = re.compile(
    r"\[(?:来源|引用)[：:\s]*(\d+)\]"
    r"|(?<![A-Za-z0-9_])chunk_id(?:\s*[:：]\s*|\s+)([0-9]+)(?![A-Za-z0-9_.%])"
)
