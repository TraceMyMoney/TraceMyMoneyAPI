from src.workers.core.send_expenses_emails.build_excel_and_send_email import (
    build_excel_and_send_email_task,
)

subscriber_methods = dict(
    build_excel_and_send_email=build_excel_and_send_email_task,
)
