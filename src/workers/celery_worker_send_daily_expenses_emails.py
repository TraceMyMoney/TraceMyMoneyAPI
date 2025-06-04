from src.workers.core.common_constants import WorkerQueueConfiguration
from src.workers.utils.celery_methods import (
    CeleryGenericBaseTask,
    events_task_initializer,
)
from src.workers.pubsub.event_consumer import process_event
from src.workers.celery_app import celery_app as event_app


@event_app.task(
    bind=True, base=CeleryGenericBaseTask,
    name=WorkerQueueConfiguration["send_daily_emails"].value["task_name"],
    routing_key="daily_expenses_notifications_queue"
)
@events_task_initializer(event_app)
def send_emails_task(self, *args, **kwargs):
    process_event(self, kwargs)
