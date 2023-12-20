from os import environ
from pathlib import Path

class BaseConfig:
    BASE_DIR = Path(__file__).parent.parent

    # Mongo
    MONGO_DATABASE_URI = environ.get(
        'MONGO_DATABASE_URI', 'mongodb://localhost:27017/')
    MONGO_DATABASE = environ.get('MONGO_DATABASE', 'trackmoney_api')
    # JWT_SECRET_KEY = environ.get(
    #     'JWT_SECRET_KEY', 'TgZdibSpYRkUrXl7')


class DevelopmentConfig(BaseConfig):
    DEBUG = True

class ProductionConfig(BaseConfig):
    DEBUG = False

class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    MONGO_DATABASE = environ.get('MONGO_DATABASE', 'test_trackthemoney')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'test': TestConfig
}
