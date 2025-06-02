from enum import Enum

WorkerQueueConfiguration = Enum(
    "WorkerQueueConfiguration",
    {
        "send_daily_emails": dict(
            task_name="send_emails_task",
            queue_name="daily_expenses_notifications_queue",
        )
    },
)
