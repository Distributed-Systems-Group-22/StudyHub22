
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException

from app.database import get_connection, init_db
from app.routes.summaries import router as summaries_router
from app.routes.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="StudyHub Synthesis Service",
    version="0.3.0",
    lifespan=lifespan
)

app.include_router(summaries_router)
app.include_router(jobs_router)


@app.get("/")
def root():
    return {
        "service": "synthesis",
        "status": "running",
        "version": "0.3.0"
    }


@app.get("/health")
def health():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return {
            "status": "healthy",
            "database": "connected"
        }

    except psycopg.Error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable"
        )
