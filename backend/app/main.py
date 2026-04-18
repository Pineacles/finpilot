from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import auth, health, dashboard, portfolio, sync, transactions, finance, agent, analysis, user_settings, stats, csv_import, categorize, merchants, docs, journal, tools
from app.core.config import settings
from app.services.gmail_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title="FinPilot",
    description="Finance & Stock Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(portfolio.router)
app.include_router(sync.router)
app.include_router(transactions.router)
app.include_router(finance.router)
app.include_router(agent.router)
app.include_router(analysis.router)
app.include_router(user_settings.router)
app.include_router(stats.router)
app.include_router(csv_import.router)
app.include_router(categorize.router)
app.include_router(merchants.router)
app.include_router(docs.router)
app.include_router(portfolio.public_router)
app.include_router(journal.router)
app.include_router(tools.router)
