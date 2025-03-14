from flask import Flask
from os import environ

from src.config import config
from src.helpers.helper import configure_logging
from src.blueprints.banks import bank_bp
from src.blueprints.expenses import expense_bp
from src.blueprints.expense_entry_tags import entry_tags_bp
from src.blueprints.auth import auth_bp
from src.signals import expense_signals, user_signals

import src.extensions as ext


def create_app():
    app = Flask(__name__)

    env = environ.get("TRACKTHEMONEY_ENV", "development")
    app_config = config[env]
    ext.connect_mongo()
    app.config.from_object(app_config)

    app.config.from_mapping(
        CELERY=dict(
            broker_url=environ.get(
                "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
            ),
            result_backend=environ.get(
                "MONGO_DATABASE_URI", "mongodb://localhost:27017/"
            ),
            task_ignore_result=True,
        )
    )

    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(bank_bp, url_prefix="/banks")
    app.register_blueprint(expense_bp, url_prefix="/expenses")
    app.register_blueprint(entry_tags_bp, url_prefix="/entry-tags")

    configure_logging(app)
    # celery_app = ext.celery_init_app(app)

    return app
