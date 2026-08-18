from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.routers.auth import router as auth_router
from app.routers.appointments import router as appointment_router
from app.routers.patients import router as patient_router
from app.routers.doctor_schedules import router as doctor_schedule_router
from app.routers.queues import router as queue_router

app = FastAPI(
    title=settings.app_name,
    description=(
        "Educational AI-powered hospital management "
        "and smart queue management system."
    ),
    version="1.0.0",
)


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    return {
        "message": "AI Hospital Management & Smart Queue API",
        "status": "running",
    }


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
    }


@app.get("/health/database", tags=["System"])
def database_health(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    result = db.execute(text("SELECT 1")).scalar_one()

    return {
        "status": "healthy",
        "database": "connected",
        "result": result,
    }


app.include_router(auth_router)


app.include_router(patient_router)

app.include_router(appointment_router)

app.include_router(doctor_schedule_router)

app.include_router(queue_router)
