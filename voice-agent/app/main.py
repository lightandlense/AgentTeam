from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.middleware.retell_auth import RetellAuthMiddleware
from app.routers import retell as retell_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables created by migrations/001_initial.sql in production.
    # In dev/test, we skip auto-create to keep SQL migration as source of truth.
    yield
    await engine.dispose()


app = FastAPI(title="Voice Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(RetellAuthMiddleware)

app.include_router(retell_router.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
