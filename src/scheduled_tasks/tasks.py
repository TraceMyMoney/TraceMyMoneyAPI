from datetime import datetime, timedelta

from src.main import create_app
from src.scheduled_tasks.core.expenses_data import get_expenses_data
from src.publishers.event_publisher import EventPublisher
from src.common_constants.pub_sub_constants import SEND_EMAILS_TASK


_, celery = create_app()


@celery.task(name="src.scheduled_tasks.tasks.send_daily_expenses_data")
def send_daily_expenses_data():
    start_date = datetime.combine(
        datetime.utcnow().date() - timedelta(days=3), datetime.min.time()
    )
    end_date = datetime.combine(
        datetime.utcnow().date() - timedelta(days=1), datetime.max.time()
    )
    aggregated_expenses_report_data = get_expenses_data(start_date, end_date)
    aggregated_expenses_report_data.update({
        "start_date": str(start_date).replace("-", "/"),
        "end_date": str(end_date).replace("-", "/")
    })

    EventPublisher().publish_message_to_exchange(
        model_instance="build_excel_and_send_email",
        task=SEND_EMAILS_TASK,
        data=aggregated_expenses_report_data,
        exchange="",
        routing_key="daily_expenses_notifications_queue",
    )
