from src.main import create_app
from celery.schedules import crontab

_, celery = create_app()


@celery.task(name="src.tasks.task.print_hello")
def print_hello():
    print("Hello from Celery Beat!")
