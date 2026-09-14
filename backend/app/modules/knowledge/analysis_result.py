from pydantic import BaseModel, ConfigDict, Field


class AnalysisCitation(BaseModel):
    chunk_id: int = Field(gt=0)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    answer: str = Field(min_length=1)
    citations: list[AnalysisCitation] = Field(min_length=1)
