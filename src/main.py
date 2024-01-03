# Import the libraries
from flask import Flask, jsonify
from os import environ
from config import config
import extensions
from blueprints.banks import bank_bp
from blueprints.expenses import expense_bp
from signals import expense_signals

# set env
env = environ.get('TRACKTHEMONEY_ENV', 'local')

def create_app(config_name):
    # Flask app object
    app = Flask(__name__)


    extensions.connect_mongo()
    app.config.from_object(config[config_name])

    app.config.from_mapping(
        CELERY=dict(
            broker_url=environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//'),
            result_backend=environ.get('MONGO_DATABASE_URI', 'mongodb://localhost:27017/'),
            task_ignore_result=True
        )
    )

    # register blueprints
    app.register_blueprint(bank_bp, url_prefix='/banks')
    app.register_blueprint(expense_bp, url_prefix='/expenses')

    return app

if env == 'test':
    app = create_app('test')
elif env == 'production':
    app = create_app('production')
else:
    app = create_app('development')

celery_app = extensions.celery_init_app(app)
