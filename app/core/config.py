import json
from os import environ

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = environ.get("PROJECT_NAME", "Stalk My Money API")
    VERSION: str = environ.get("VERSION", "1.0.0")
    DEBUG: bool = environ.get("DEBUG", False)

    # MongoDB (current backend; being migrated to PostgreSQL per PLAN.md)
    MONGODB_URL: str = environ.get("MONGODB_URL", "mongodb://admin:jKFLXJCoGgsVCoiO@localhost:27017/")
    MONGODB_DB_NAME: str = environ.get("MONGODB_DB_NAME", "trackmoney_api")

    # PostgreSQL (migration target; see PLAN.md)
    DATABASE_URL: str = environ.get("DATABASE_URL", "postgresql+asyncpg://smm:smm@localhost:5432/stalk_my_money")

    # Security
    SECRET_KEY: str = environ.get("SECRET_KEY", "this_is_secret_key")
    ALGORITHM: str = environ.get("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7)

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = environ.get(
        "BACKEND_CORS_ORIGINS",
        ["http://localhost:5173", "http://127.0.0.1:5173", "https://app.stalk-my-money.in"],
    )

    # Optional: Celery
    CELERY_BROKER_URL: str = environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    GROQ_API_KEY: str = environ.get("GROQ_API_KEY", "test_api_key")

    # Read incoming bank SMS with the admin-configured chat model (falling back
    # to the fixed patterns if it is unavailable). Set to "false" to turn off.
    SMS_AI_PARSING: bool = environ.get("SMS_AI_PARSING", "true").lower() not in ("0", "false", "no")
    GROQ_MODEL_NAME: str = environ.get("GROQ_MODEL_NAME", "test_model_name")

    # Optional: other chat-LLM providers an admin can switch to from the
    # admin dashboard (see app/core/llm.py). Credentials stay in .env, not
    # the DB - the DB only ever stores *which* provider/model is active,
    # never a secret. A provider with no key set here simply can't be
    # selected (see AppSettingsService.get_ai_config's validation).
    OPENAI_API_KEY: str = environ.get("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = environ.get("ANTHROPIC_API_KEY", "")
    OPENROUTER_API_KEY: str = environ.get("OPENROUTER_API_KEY", "")

    # Optional: TypeSafe AI's Jev decision model (see app/core/jev.py). Left
    # unset, every Jev-dependent feature (tag suggestion, chat tool-subset
    # routing, write-action risk flagging, fast-path commands) silently
    # no-ops - nothing in the app hard-depends on this being configured.
    TYPESAFE_API_KEY: str = environ.get("TYPESAFE_API_KEY", "")

    # OAuth / MCP connector. API_BASE_URL is this API's public URL (used to
    # build the OAuth metadata Claude fetches); FRONTEND_BASE_URL is where the
    # "Authorize Claude?" page lives. Claude may only be redirected to hosts
    # in OAUTH_ALLOWED_REDIRECT_HOSTS (comma separated, subdomains included).
    API_BASE_URL: str = environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
    FRONTEND_BASE_URL: str = environ.get("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    OAUTH_ALLOWED_REDIRECT_HOSTS: str = environ.get(
        "OAUTH_ALLOWED_REDIRECT_HOSTS", "claude.ai,claude.com,localhost,127.0.0.1"
    )

    # Transactional email via the Mailgun HTTP API (same variable names as
    # obsidian-clone). If any of the three is empty the app falls back to a
    # console backend that just logs the email (and its link) - nothing is sent.
    MAILGUN_API_KEY: str = environ.get("MAILGUN_API_KEY", "")
    MAILGUN_URI: str = environ.get("MAILGUN_URI", "")
    MAILGUN_FROM_ADDR: str = environ.get("MAILGUN_FROM_ADDR", "")
    EMAIL_FROM_NAME: str = environ.get("EMAIL_FROM_NAME", "Stalk My Money")
    # Background email worker (the outbox poller). Tests turn it off.
    EMAIL_WORKER_ENABLED: bool = environ.get("EMAIL_WORKER_ENABLED", "true").lower() not in ("0", "false", "no")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Parse BACKEND_CORS_ORIGINS if it's a string
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            try:
                self.BACKEND_CORS_ORIGINS = json.loads(self.BACKEND_CORS_ORIGINS)
            except json.JSONDecodeError:
                self.BACKEND_CORS_ORIGINS = [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")]


settings = Settings()
