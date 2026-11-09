# backend/app/main.py
from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="CaseMind API", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """PRD Section 12: liveness probe used by Docker health checks."""
    return {"status": "ok"}
