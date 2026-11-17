from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    from .settings import settings
except ImportError:  # Supports execution as ``uvicorn main:app`` inside the container.
    from settings import settings


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class IncidentSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(StrEnum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160, examples=["API readiness check failed"])
    description: str = Field(default="", max_length=2_000)
    severity: IncidentSeverity = IncidentSeverity.medium


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus


class Incident(BaseModel):
    id: int
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


CREATE_INCIDENTS_TABLE = """
CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status VARCHAR(16) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'resolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.execute(text(CREATE_INCIDENTS_TABLE))
    yield
    await engine.dispose()


app = FastAPI(
    title="Infrastructure Lab API",
    version="0.2.0",
    lifespan=lifespan,
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Number of HTTP requests handled by the API",
    ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)


@app.middleware("http")
async def collect_request_metrics(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    path = request.url.path
    REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
    REQUEST_DURATION.labels(request.method, path).observe(perf_counter() - started)
    return response


@app.get("/health", tags=["operations"])
async def health_check() -> dict[str, str]:
    """Liveness check: confirms that the API process responds."""
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
async def readiness_check() -> dict[str, str]:
    """Readiness check: confirms that PostgreSQL is reachable."""
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@app.post(
    "/incidents",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
    tags=["incidents"],
)
async def create_incident(payload: IncidentCreate) -> Incident:
    """Register an operational incident for follow-up."""
    query = text(
        """
        INSERT INTO incidents (title, description, severity)
        VALUES (:title, :description, :severity)
        RETURNING id, title, description, severity, status, created_at, updated_at
        """
    )
    async with session_factory() as session:
        result = await session.execute(
            query,
            {
                "title": payload.title,
                "description": payload.description,
                "severity": payload.severity.value,
            },
        )
        await session.commit()
        return Incident.model_validate(result.mappings().one())


@app.get("/incidents", response_model=list[Incident], tags=["incidents"])
async def list_incidents() -> list[Incident]:
    """Show incidents, placing unresolved items first."""
    query = text(
        """
        SELECT id, title, description, severity, status, created_at, updated_at
        FROM incidents
        ORDER BY (status = 'resolved'), created_at DESC
        """
    )
    async with session_factory() as session:
        result = await session.execute(query)
        return [Incident.model_validate(row) for row in result.mappings().all()]


@app.patch("/incidents/{incident_id}/status", response_model=Incident, tags=["incidents"])
async def update_incident_status(
    incident_id: int, payload: IncidentStatusUpdate
) -> Incident:
    """Move an incident through the operational response workflow."""
    query = text(
        """
        UPDATE incidents
        SET status = :status, updated_at = CURRENT_TIMESTAMP
        WHERE id = :incident_id
        RETURNING id, title, description, severity, status, created_at, updated_at
        """
    )
    async with session_factory() as session:
        result = await session.execute(
            query, {"incident_id": incident_id, "status": payload.status.value}
        )
        incident = result.mappings().one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        await session.commit()
        return Incident.model_validate(incident)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint; reachable only from the internal Docker network."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
