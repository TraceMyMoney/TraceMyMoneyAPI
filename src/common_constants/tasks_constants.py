from celery.schedules import crontab

SCHEDULED_TASKS = {
    "send_daily_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_daily_expenses_data",
        "schedule": crontab(hour=0, minute=1),
    },
}
