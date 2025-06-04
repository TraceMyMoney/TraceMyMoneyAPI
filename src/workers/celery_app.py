from src.main import create_app
from flask_celeryext import FlaskCeleryExt
from src.extensions import config

app, _ = create_app()
ext = FlaskCeleryExt(app)
celery_app = ext.celery
celery_app.conf.broker_url = config['EVENT_CELERY_BROKER_URL']
