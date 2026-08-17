from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db


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
