from mongoengine import NotUniqueError
from flask import current_app as app
from src.workers.core.common_functions import subscriber_methods


def process_event(self, kwargs):
    model, data, exchange = (
        kwargs["model"],
        kwargs["data"],
        kwargs["callback_exchange"],
    )
    try:
        record_object = subscriber_methods[model](self, data, exchange)
    except NotUniqueError as e:
        message = str(e)
        raise NotUniqueError(f"{message}")
    except KeyError as e:
        message = str(e)
        raise KeyError(f"{message}")

    # if record_object:
    #     self.logger.info(f"Processed data - {kwargs}")
    #     self.logger.info(
    #         f"Result is for model {model} with action {action} and object"
    #         f" {record_object}"
    #     )
