import requests
from flask import current_app as app


def send_email(to_addr, subject, content):
    return requests.post(
        app.config["MAILGUN_URI"],
        auth=("api", app.config["MAILGUN_API_KEY"]),
        data={
            "from": app.config["MAILGUN_FROM_ADDR"],
            "to": to_addr,
            "subject": subject,
            "text": content,
        },
    )
