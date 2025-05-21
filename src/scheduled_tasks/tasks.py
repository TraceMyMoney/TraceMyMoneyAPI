from datetime import datetime, timedelta

from src.main import create_app
from src.scheduled_tasks.core.expenses_data import get_expenses_data


_, celery = create_app()


@celery.task(name="src.scheduled_tasks.tasks.send_daily_expenses_data")
def send_daily_expenses_data():
    start_date = datetime.combine(
        datetime.utcnow().date() - timedelta(days=1), datetime.min.time()
    )
    end_date = datetime.combine(
        datetime.utcnow().date() - timedelta(days=1), datetime.max.time()
    )
    some = get_expenses_data(start_date, end_date)
    # get the aggregated data
    # if data: then => publish it to build_csv_and_send_email worker.
