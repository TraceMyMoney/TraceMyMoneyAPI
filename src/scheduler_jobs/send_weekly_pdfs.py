from src.extensions import scheduler
from apscheduler.triggers.cron import CronTrigger


@scheduler.task(id="send_weekly_pdfs", trigger=CronTrigger(minute="*"))
def send_weekly_pdfs():
    print("Sending the weekly pdf")
