import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def provide_todays_date(provided_date=None, str_format=True):
    custom_date = provided_date or datetime.now()
    return (
        f"{custom_date.day:02}-{custom_date.month:02}-{custom_date.year} 00:00"
        if str_format
        else (custom_date.year, custom_date.month, custom_date.day)
    )


def configure_logging(app, file_name=None):
    for handler in app.logger.handlers[:]:
        app.logger.removeHandler(handler)

    log_level = logging.DEBUG if app.config["DEBUG"] else logging.INFO
    log_file = file_name if file_name else "app.log"

    handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        "\n%(asctime)s - %(name)s - %(levelname)s - %(message)s"\
        "\n--------------------------------------------------------"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    if app.config["DEBUG"]:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
