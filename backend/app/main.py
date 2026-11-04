import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.endpoints import auth, health, dashboard, portfolio, portfolio_sharing, sync, transactions, finance, agent, user_settings, stats, csv_import, categorize, merchants, docs, brokers, watchlist
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.services.gmail_scheduler import start_scheduler as start_gmail_scheduler, stop_scheduler as stop_gmail_scheduler
from app.services.saxo_scheduler import start_scheduler as start_saxo_scheduler, stop_scheduler as stop_saxo_scheduler

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_client_ip)


def _validate_settings() -> None:
    """Raise a clear error at startup if critical settings are misconfigured."""
    weak = {"change-me-in-production", "change-me", ""}
    key = settings.SECRET_KEY
    if not key or key in weak or len(key) < 32:
        raise RuntimeError(
            "SECRET_KEY is missing or too weak. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "and set it in your .env file."
        )
    if not settings.TOKEN_ENCRYPTION_KEY.strip():
        logger.warning(
            "TOKEN_ENCRYPTION_KEY is empty: Gmail, Saxo, AI and agent credentials "
            "are stored in plaintext in the database. Set a Fernet key to encrypt them."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_settings()
    start_gmail_scheduler()
    start_saxo_scheduler()
    yield
    stop_saxo_scheduler()
    stop_gmail_scheduler()


# Disable interactive API docs in production (set ENVIRONMENT=production in .env to activate)
_docs_url = None if settings.ENVIRONMENT == "production" else "/docs"
_redoc_url = None if settings.ENVIRONMENT == "production" else "/redoc"

app = FastAPI(
    title="FinPilot",
    description="Finance & Stock Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
app.include_router(user_settings.router)
app.include_router(stats.router)
app.include_router(csv_import.router)
app.include_router(categorize.router)
app.include_router(merchants.router)
app.include_router(docs.router)
app.include_router(portfolio_sharing.public_router)
app.include_router(brokers.router)
app.include_router(watchlist.router)
