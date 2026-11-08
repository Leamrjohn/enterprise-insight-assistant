"""The bounded, fact-led input Knowledge may use for document retrieval."""

from pydantic import BaseModel, Field


class RetrievalBrief(BaseModel):
    question: str = Field(min_length=1)
    confirmed_fact_ids: list[str] = Field(default_factory=list)
    confirmed_fact_statements: list[str] = Field(default_factory=list)

    def render_query(self) -> str:
        if not self.confirmed_fact_statements:
            return self.question
        return (
            f"用户问题：{self.question}\n"
            "已确认经营事实（仅用于检索可能解释，不构成因果结论；"
            "不得因资料未复述上述事实而否定或限定它）：\n- "
            + "\n- ".join(self.confirmed_fact_statements)
        )
