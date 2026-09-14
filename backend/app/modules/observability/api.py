"""Company-admin operational telemetry API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.organizations.access import CurrentCompanyContext, require_admin
from app.db.session import get_db
from app.modules.observability.schemas import TaskMetricsOut
from app.modules.observability.service import get_company_task_metrics


router = APIRouter()


@router.get("/observability/task-metrics", response_model=TaskMetricsOut)
def get_task_metrics_endpoint(
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TaskMetricsOut:
    return get_company_task_metrics(db, company_id=context.company.id)
