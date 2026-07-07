from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://finpilot:finpilot_dev@localhost:5432/finpilot"
    SECRET_KEY: str = ""
    ENVIRONMENT: str = "development"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Comma-separated CORS origins (e.g. "http://localhost:3000,https://your-domain.example.com")
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3010"

    # Saxo Bank
    SAXO_APP_KEY: str = ""
    SAXO_APP_SECRET: str = ""
    SAXO_CERT_PATH: str = ""
    SAXO_ACCOUNT_KEY: str = ""
    SAXO_TOKEN_URL: str = "https://live.logonvalidation.net/token"
    SAXO_API_URL: str = "https://gateway.saxobank.com/openapi"

    # Viseca One
    VISECA_USERNAME: str = ""
    VISECA_PASSWORD: str = ""
    VISECA_API_URL: str = "https://api.one.viseca.ch/v1"

    # AI Analysis
    ANTHROPIC_API_KEY: str = ""
    ANALYSIS_MODEL: str = "claude-sonnet-4-20250514"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
