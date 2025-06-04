from datetime import datetime, timedelta

from src.main import create_app
from src.scheduled_tasks.core.expenses_data import get_expenses_data
from src.publishers.event_publisher import EventPublisher
from src.common_constants.pub_sub_constants import SEND_EMAILS_TASK


_, celery = create_app()


@celery.task(name="src.scheduled_tasks.tasks.send_daily_expenses_data")
def send_daily_expenses_data():
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    start_date = datetime.combine(yesterday, datetime.min.time())
    end_date = datetime.combine(yesterday, datetime.max.time())

    _publish_expenses_report(start_date, end_date, "daily_report")


@celery.task(name="src.scheduled_tasks.tasks.send_weekly_expenses_data")
def send_weekly_expenses_data():
    today = datetime.utcnow().date()  # Task runs on Sunday
    last_sunday = today - timedelta(days=7)
    last_saturday = today - timedelta(days=1)
    start_date = datetime.combine(last_sunday, datetime.min.time())
    end_date = datetime.combine(last_saturday, datetime.max.time())

    _publish_expenses_report(start_date, end_date, "weekly_report")


@celery.task(name="src.scheduled_tasks.tasks.send_monthly_expenses_data")
def send_monthly_expenses_data():
    today = datetime.utcnow().date()  # Today is the 1st of the current month
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_day_last_month.replace(day=1)
    start_date = datetime.combine(first_day_last_month, datetime.min.time())
    end_date = datetime.combine(last_day_last_month, datetime.max.time())

    _publish_expenses_report(start_date, end_date, "monthly_report")


def _publish_expenses_report(start_date, end_date, report_name):
    print(f"start_date, end_date: {start_date, end_date}")
    data = get_expenses_data(start_date, end_date)
    data.update(
        {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "report_name": report_name,
        }
    )
    EventPublisher().publish_message_to_exchange(
        model_instance="build_excel_and_send_email",
        task=SEND_EMAILS_TASK,
        data=data,
        exchange="",
        routing_key="daily_expenses_notifications_queue",
    )
