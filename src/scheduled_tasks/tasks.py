from datetime import datetime, timedelta

from src.main import create_app
from src.scheduled_tasks.core.expenses_data import get_expenses_data


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
    # TODO:
    # publish this aggregated_expenses_report_data
    # create the create_excel_and_send_email worker as a consumer
