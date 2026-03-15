from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "Stalk My Money API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # MongoDB
    MONGODB_URL: str = "mongodb://admin:jKFLXJCoGgsVCoiO@localhost:27017/"
    MONGODB_DB_NAME: str = "stalk_my_money"

    # Security
    SECRET_KEY: str = "this_is_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = []

    # Optional: Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

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
