from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    from .settings import settings
except ImportError:  # Supports execution as ``uvicorn main:app`` inside the container.
    from settings import settings


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Infrastructure Lab API",
    version="0.1.0",
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


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint; reachable only from the internal Docker network."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
