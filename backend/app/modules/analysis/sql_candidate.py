from pydantic import BaseModel, Field

from app.modules.analysis.query_contract import QueryContract


class SQLCandidate(BaseModel):
    """LLM 为一次经营数据查询生成的候选结果。"""

    sql: str = Field(
        min_length=1,
        max_length=8_000,
        description="待校验的 PostgreSQL SELECT 查询。",
    )
    purpose: str = Field(
        min_length=1,
        max_length=300,
        description="这条 SQL 要验证的业务问题。",
    )
    query_contract: QueryContract | None = Field(
        default=None,
        description="候选查询应返回的业务证据契约。",
    )
