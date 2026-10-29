from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from routers import wqi_weight
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from core.config import settings
from core.error_handler import register_exception_handlers
from core.exceptions import ServiceUnavailableError
from core.rate_limiter import limiter
from core.http_audit_middleware import HTTPAuditMiddleware
from database import get_db
from routers.alert import router as alert_router
from routers.auth import router as auth_router
from routers.device import router as device_router
from routers.incident import router as incidents_router
from routers.lab_test import router as lab_tests_router
from routers.maintenance_record import router as maintenance_records_router
from routers.sensor_reading_router import router as sensor_reading_router
from routers.users import admin_router, router as users_router
from routers.audit_logs import router as audit_logs_router


app = FastAPI(title="AquaTrace API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(HTTPAuditMiddleware)
app.state.limiter = limiter


register_exception_handlers(app)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(device_router, prefix="/api/v1")
app.include_router(incidents_router)
app.include_router(maintenance_records_router)
app.include_router(lab_tests_router)
app.include_router(alert_router)
app.include_router(audit_logs_router)
app.include_router(sensor_reading_router)
app.include_router(wqi_weight.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise ServiceUnavailableError("Database unavailable") from None
    return {"status": "ok"}
