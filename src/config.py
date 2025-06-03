from os import environ
from pathlib import Path


class BaseConfig:
    BASE_DIR = Path(__file__).parent.parent

    # Mongo
    MONGO_DATABASE_URI = environ.get("MONGO_DATABASE_URI", "mongodb://localhost:27017/")
    MONGO_DATABASE = environ.get("MONGO_DATABASE", "trackmoney_api")
    JWT_SECRET_KEY = environ.get("JWT_SECRET_KEY", "TgZdibSpYRkUrXl7")
    DAILY_EXPENSES_NOTIFICATIONS_QUEUE = environ.get(
        "DAILY_EXPENSES_NOTIFICATIONS_QUEUE", "daily_expenses_notifications_queue"
    )

    # celery
    EVENT_RABBITMQ_HOST = environ.get("EVENT_RABBITMQ_HOST", "localhost")
    EVENT_RABBITMQ_USERNAME = environ.get("EVENT_RABBITMQ_USERNAME", "guest")
    EVENT_RABBITMQ_PASSWORD = environ.get("EVENT_RABBITMQ_PASSWORD", "guest")
    EVENT_RABBITMQ_VHOST = environ.get("EVENT_RABBITMQ_VHOST", "/")
    EVENT_RABBITMQ_PROTOCOL = environ.get("EVENT_RABBITMQ_PROTOCOL", "amqp")
    EVENT_RABBITMQ_PORT = environ.get("EVENT_RABBITMQ_PORT", "5672")

    EVENT_CELERY_BROKER_URL = "{}://{}:{}@{}:{}/{}".format(
        EVENT_RABBITMQ_PROTOCOL,
        EVENT_RABBITMQ_USERNAME,
        EVENT_RABBITMQ_PASSWORD,
        EVENT_RABBITMQ_HOST,
        EVENT_RABBITMQ_PORT,
        EVENT_RABBITMQ_VHOST,
    )
    AWS_ACCESS_KEY_ID = environ.get("AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = environ.get(
        "AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"
    )
    EXCEL_UPLOAD_PATH = environ.get("EXCEL_UPLOAD_PATH", "EXCEL_UPLOAD_PATH")
    AWS_BUCKET_NAME = environ.get("AWS_BUCKET_NAME", "AWS_BUCKET_NAME")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    MONGO_DATABASE = environ.get("MONGO_DATABASE", "trackmoney_api_test")


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "test": TestConfig,
}
