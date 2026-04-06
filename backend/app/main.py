from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import auth, health, dashboard, portfolio, sync, transactions, finance, agent, analysis
from app.core.config import settings

app = FastAPI(
    title="FinPilot",
    description="Finance & Stock Dashboard API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
