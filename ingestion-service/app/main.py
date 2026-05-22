"""
Ingestion Service — FastAPI app.

Responsibilities:
  1. Background task: consume Redis Streams and write inference_logs to DB
  2. REST API: expose metrics for dashboards (latency, throughput, errors)
  3. REST API: direct ingest endpoint (for SDK fallback when Redis is down)
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.config import settings
from app.database import get_db, engine, Base
from app.models import InferenceLog
from app.redis_consumer import run_consumer
from app.pipeline import process_event, InferenceEventSchema

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

_consumer_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task
    # Ensure tables exist (shared schema)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Start event consumer in background
    _consumer_task = asyncio.create_task(run_consumer())
    logger.info("Ingestion service started.")
    yield
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    logger.info("Ingestion service stopped.")


app = FastAPI(title="Ingestion Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Direct ingest fallback ────────────────────────────────────────────────────

class DirectIngestRequest(BaseModel):
    event: dict


@app.post("/ingest", status_code=202)
async def direct_ingest(body: DirectIngestRequest):
    """Fallback endpoint: SDK posts directly when Redis is unavailable."""
    ok = await process_event(body.event)
    if not ok:
        raise HTTPException(status_code=422, detail="Event validation failed")
    return {"status": "accepted"}


# ── Metrics API ────────────────────────────────────────────────────────────────

def _parse_window(window: str) -> datetime:
    """Convert '1h', '24h', '7d' to a UTC cutoff datetime."""
    now = datetime.utcnow()
    if window.endswith("h"):
        return now - timedelta(hours=int(window[:-1]))
    if window.endswith("d"):
        return now - timedelta(days=int(window[:-1]))
    return now - timedelta(hours=1)


@app.get("/metrics/summary")
async def metrics_summary(window: str = "1h", db: AsyncSession = Depends(get_db)):
    since = _parse_window(window)
    base = select(InferenceLog).where(InferenceLog.timestamp >= since)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    errors = (await db.execute(
        select(func.count()).where(and_(InferenceLog.timestamp >= since, InferenceLog.status == "error"))
    )).scalar()
    avg_latency = (await db.execute(
        select(func.avg(InferenceLog.latency_ms)).where(InferenceLog.timestamp >= since)
    )).scalar()
    p99_latency = (await db.execute(
        select(func.percentile_cont(0.99).within_group(InferenceLog.latency_ms.asc()))
        .where(InferenceLog.timestamp >= since)
    )).scalar()
    total_tokens = (await db.execute(
        select(func.sum(InferenceLog.total_tokens)).where(InferenceLog.timestamp >= since)
    )).scalar()

    return {
        "window": window,
        "total_requests": total or 0,
        "error_count": errors or 0,
        "error_rate": round((errors or 0) / max(total or 1, 1) * 100, 2),
        "avg_latency_ms": round(avg_latency or 0, 2),
        "p99_latency_ms": round(p99_latency or 0, 2),
        "total_tokens": total_tokens or 0,
    }


@app.get("/metrics/latency")
async def metrics_latency(window: str = "1h", db: AsyncSession = Depends(get_db)):
    """Latency trend: 20 time buckets over the window."""
    since = _parse_window(window)
    result = await db.execute(
        select(
            InferenceLog.timestamp,
            InferenceLog.latency_ms,
            InferenceLog.provider,
        )
        .where(InferenceLog.timestamp >= since)
        .order_by(InferenceLog.timestamp)
    )
    rows = result.all()
    return [{"timestamp": r.timestamp.isoformat(), "latency_ms": r.latency_ms, "provider": r.provider} for r in rows]


@app.get("/metrics/throughput")
async def metrics_throughput(window: str = "1h", db: AsyncSession = Depends(get_db)):
    """Request counts grouped by minute."""
    since = _parse_window(window)
    result = await db.execute(
        select(
            func.date_trunc("minute", InferenceLog.timestamp).label("bucket"),
            func.count().label("count"),
        )
        .where(InferenceLog.timestamp >= since)
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = result.all()
    return [{"bucket": r.bucket.isoformat(), "count": r.count} for r in rows]


@app.get("/metrics/errors")
async def metrics_errors(window: str = "1h", db: AsyncSession = Depends(get_db)):
    """Error breakdown by provider."""
    since = _parse_window(window)
    result = await db.execute(
        select(
            InferenceLog.provider,
            InferenceLog.error_message,
            InferenceLog.timestamp,
        )
        .where(and_(InferenceLog.timestamp >= since, InferenceLog.status == "error"))
        .order_by(InferenceLog.timestamp.desc())
        .limit(100)
    )
    rows = result.all()
    return [{"provider": r.provider, "error": r.error_message, "timestamp": r.timestamp.isoformat()} for r in rows]


@app.get("/metrics/by-provider")
async def metrics_by_provider(window: str = "24h", db: AsyncSession = Depends(get_db)):
    since = _parse_window(window)
    result = await db.execute(
        select(
            InferenceLog.provider,
            func.count().label("requests"),
            func.avg(InferenceLog.latency_ms).label("avg_latency"),
            func.sum(InferenceLog.total_tokens).label("total_tokens"),
            func.sum(
                (InferenceLog.status == "error").cast(__import__("sqlalchemy").Integer)
            ).label("errors"),
        )
        .where(InferenceLog.timestamp >= since)
        .group_by(InferenceLog.provider)
    )
    rows = result.all()
    return [
        {
            "provider": r.provider,
            "requests": r.requests,
            "avg_latency_ms": round(r.avg_latency or 0, 2),
            "total_tokens": r.total_tokens or 0,
            "errors": r.errors or 0,
        }
        for r in rows
    ]


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ingestion"}
