from celery.schedules import crontab

SCHEDULED_TASKS = {
    "send_daily_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_daily_expenses_data",
        "schedule": crontab(minute="*/1"),
    },
    "send_weekly_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_weekly_expenses_data",
        "schedule": crontab(minute="*/2"),
    },
    "send_monthly_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_monthly_expenses_data",
        "schedule": crontab(minute="*/3"),
    },
}
