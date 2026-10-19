from app.db.session import get_db
from app.modules.observability.health_schemas import HealthResponse
from app.modules.observability.health_service import get_readiness_service
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health():
    return {"status": "ok"}


@router.get("/health/live", response_model=HealthResponse)
def get_liveness():
    return {"status": "ok"}


@router.get("/health/ready", response_model=HealthResponse)
def get_readiness(db: Session = Depends(get_db)):
    try:
        readiness = get_readiness_service(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc
    if readiness["status"] != "ok":
        return JSONResponse(status_code=503, content=readiness)
    return readiness
