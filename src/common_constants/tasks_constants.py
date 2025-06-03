from celery.schedules import crontab

SCHEDULED_TASKS = {
    "send_daily_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_daily_expenses_data",
        "schedule": crontab(hour=0, minute=1),
    },
    "send_weekly_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_weekly_expenses_data",
        "schedule": crontab(hour=0, minute=1, day_of_week=0),
    },
    "send_monthly_expenses_data": {
        "task": "src.scheduled_tasks.tasks.send_monthly_expenses_data",
        "schedule": crontab(hour=0, minute=1, day_of_month=1),
    },
}

EMAIL_SUBJECT = "Expenses report for {report_name}"
EMAIL_CONTENT = "Dear {user_name}, \n\nPlease find your expenses report here :\n\n{file_url}"
