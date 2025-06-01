from src.extensions import config

# configs
DAILY_EXPENSES_NOTIFICATIONS_EXCHANGE = "daily_expenses_notifications_exchange"
DIRECT = "direct"

# tasks
SEND_EMAILS_TASK = "send_emails_task"


DAILY_EXPENSES_NOTIFICATIONS_EXCHANGE_QUEUE_BINDING = dict(
    exchange=DAILY_EXPENSES_NOTIFICATIONS_EXCHANGE,
    queues=[
        config.get("DAILY_EXPENSES_NOTIFICATIONS_QUEUE"),
    ],
    type=DIRECT,
)


EXCHANGE_QUEUE_BINDING = [
    DAILY_EXPENSES_NOTIFICATIONS_EXCHANGE_QUEUE_BINDING,
]
