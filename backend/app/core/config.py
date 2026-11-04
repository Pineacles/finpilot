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

    # Fernet key(s) (comma-separated; the first encrypts, all decrypt) used to
    # encrypt gmail_app_password and saxo_access_token at rest. Empty = those
    # values are stored in plaintext. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing the key makes the encrypted settings unreadable (re-enter them).
    TOKEN_ENCRYPTION_KEY: str = ""

    # Hostnames that user-supplied AI/search URLs may reach even though they
    # resolve to private addresses (e.g. "ollama,searxng,host.docker.internal").
    # Everything else must resolve to a public address (SSRF guard).
    ALLOWED_PRIVATE_HOSTS: str = ""

    # Honour CF-Connecting-IP / X-Forwarded-For for rate limiting. Off by
    # default: only enable when every request reaches the app through a proxy
    # that sets or overwrites those headers (e.g. a Cloudflare tunnel in front
    # of the web container). Otherwise a client can pick its own rate bucket.
    TRUST_PROXY_HEADERS: bool = False

    # AI Analysis
    ANTHROPIC_API_KEY: str = ""
    ANALYSIS_MODEL: str = "claude-haiku-4-5-20251001"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
