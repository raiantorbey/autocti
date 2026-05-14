"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse

from backend.api import admin, auth, feedback, graph, incidents, realtime
from backend.api import sensor as sensor_api
from backend.core.config import settings
from backend.core.logging import logger, setup_logging
from backend.db.chroma_client import vector_store
from backend.db.neo4j_client import neo4j_client
from backend.db.postgres import init_db
from backend.db.redis_client import close_redis, get_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.app_name} ({settings.app_env})")

    try:
        await init_db()
        logger.info("Postgres schema ready")
    except Exception as e:
        logger.error(f"Postgres init failed: {e}")

    try:
        await neo4j_client.connect()
    except Exception as e:
        logger.warning(f"Neo4j init failed (continuing): {e}")

    try:
        vector_store.connect()
    except Exception as e:
        logger.warning(f"Vector store init failed: {e}")

    try:
        await get_redis()
    except Exception as e:
        logger.warning(f"Redis init failed: {e}")

    # Notify any already-connected websocket clients we're alive
    try:
        await realtime.emit(
            "system",
            msg="backend_ready",
            services={
                "postgres": True,
                "neo4j": True,
                "redis": True,
                "chroma": True,
            },
        )
    except Exception:
        pass

    yield

    await neo4j_client.close()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Autonomous Cyber Threat Intelligence — Agentic AI SOC Framework",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(incidents.router)
app.include_router(feedback.router)
app.include_router(graph.router)
app.include_router(admin.router)
app.include_router(realtime.router)
app.include_router(sensor_api.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/")
async def root():
    return {"service": settings.app_name, "docs": "/docs", "health": "/health"}