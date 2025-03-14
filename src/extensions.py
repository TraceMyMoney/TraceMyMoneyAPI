# libraries imports
from os import environ
from flask.config import Config
from mongoengine import connect
from celery import Celery, Task
from flask_apscheduler import APScheduler

# relative imports
from src.config import config as app_config

config = Config("")
scheduler = APScheduler() # create the scheduler instance
env = environ.get("TRACKTHEMONEY_ENV", "development").lower()

if env == "test":
    config.from_object(app_config["test"])
elif env == "production":
    config.from_object(app_config["production"])
else:
    config.from_object(app_config["development"])


def connect_mongo():
    mongo_engine = connect(config["MONGO_DATABASE"], host=config["MONGO_DATABASE_URI"])
    return mongo_engine


def celery_init_app(app):
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app
