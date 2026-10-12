from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import bootstrap
from app.database import Base, SessionLocal, engine
from app.routers import activity, agents, approvals, auth, chat, dashboard, financials, integrations, missions, oversight, products, settings_router
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # safety net; alembic is the source of truth for prod
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Psalm 90:17 Commerce API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(missions.router)
app.include_router(approvals.router)
app.include_router(products.router)
app.include_router(agents.router)
app.include_router(financials.router)
app.include_router(settings_router.router)
app.include_router(activity.router)
app.include_router(chat.router)
app.include_router(oversight.router)
app.include_router(integrations.router)


@app.get("/health")
def health():
    return {"status": "ok"}
