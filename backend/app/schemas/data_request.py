from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

QueryId = Literal[
    "regional_revenue_comparison",
    "customer_revenue_drilldown",
    "category_margin_comparison",
    "quality_ticket_trend",
    "accounts_receivable_aging",
]

RegionCode = Literal["EAST", "SOUTH", "NORTH", "WEST"]


class DataRequest(BaseModel):
    query_id: QueryId
    region: RegionCode | None = None
    current_month: date
    comparison_month: date
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_months(self) -> "DataRequest":
        if self.current_month == self.comparison_month:
            raise ValueError("current_month and comparison_month must differ")

        if self.current_month.day != 1 or self.comparison_month.day != 1:
            raise ValueError("months must use the first day of the month")

        return self
