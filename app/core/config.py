import json
from pydantic_settings import BaseSettings
from typing import List
from os import environ


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = environ.get("PROJECT_NAME", "Stalk My Money API")
    VERSION: str = environ.get("VERSION", "1.0.0")
    DEBUG: bool = environ.get("DEBUG", False)

    # MongoDB
    MONGODB_URL: str = environ.get("MONGODB_URL", "mongodb://admin:jKFLXJCoGgsVCoiO@localhost:27017/")
    MONGODB_DB_NAME: str = environ.get("MONGODB_DB_NAME", "trackmoney_api")

    # Security
    SECRET_KEY: str = environ.get("SECRET_KEY", "this_is_secret_key")
    ALGORITHM: str = environ.get("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30)

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = environ.get(
        "BACKEND_CORS_ORIGINS",
        ["http://localhost:5173", "http://127.0.0.1:5173", "https://app.stalk-my-money.in"],
    )

    # Optional: Celery
    CELERY_BROKER_URL: str = environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    GROQ_API_KEY: str = environ.get("GROQ_API_KEY", "test_api_key")
    GROQ_MODEL_NAME: str = environ.get("GROQ_MODEL_NAME", "test_model_name")

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Parse BACKEND_CORS_ORIGINS if it's a string
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            try:
                self.BACKEND_CORS_ORIGINS = json.loads(self.BACKEND_CORS_ORIGINS)
            except json.JSONDecodeError:
                self.BACKEND_CORS_ORIGINS = [
                    origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")
                ]


settings = Settings()
