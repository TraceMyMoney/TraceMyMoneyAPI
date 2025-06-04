import uuid
from kombu.exceptions import ConnectionError, ChannelError
from kombu import Connection, Exchange, Queue
from flask import current_app
import json

from src.extensions import config
from src.common_constants.pub_sub_constants import EXCHANGE_QUEUE_BINDING, DIRECT


class EventPublisher:
    def __init__(
        self,
        exchange_binding: dict = None,
        host: str = None,
        port: str = None,
        vhost: str = None,
        user: str = None,
        password: str = None,
        app=None,
    ) -> None:

        self.__host = host or config["EVENT_RABBITMQ_HOST"]
        self.__port = port or config["EVENT_RABBITMQ_PORT"]
        self.__vhost = vhost or config["EVENT_RABBITMQ_VHOST"]
        self.__user = user or config["EVENT_RABBITMQ_PASSWORD"]
        self.__password = password or config["EVENT_RABBITMQ_PASSWORD"]
        self.app = app or current_app
        if exchange_binding:
            self.__individual_exchange_queue_binding(exchange_binding)

    def __get_connection(self):
        return Connection(
            hostname=self.__host,
            userid=self.__user,
            password=self.__password,
            virtual_host=self.__vhost,
            port=self.__port,
            heartbeat=0,
        )

    def __construct_message_for_non_model_instance(
        self,
        target_model_instance,
        data,
        callback_exchange=None,
        routing_key="",
        callback_routing_key="",
    ):
        x = dict(
            model=target_model_instance,
            data=data,
            callback_exchange=callback_exchange,
            routing_key=routing_key,
            callback_routing_key=callback_routing_key,
        )
        y = [[], x, {"callbacks": None, "errbacks": None, "chain": None, "chord": None}]
        return json.dumps(y)

    def __individual_exchange_queue_binding(self, exchange_binding):
        self.app.logger.info("Individual exchange queue binding")
        with self.__get_connection() as conn:
            exchange = Exchange(
                exchange_binding.get("exchange"),
                exchange_binding.get("type"),
                durable=True,
            )
            for queue in exchange_binding.get("queues", []):
                Queue(
                    queue,
                    exchange=exchange,
                    routing_key=queue if exchange_binding.get("type") == DIRECT else "",
                    durable=True,
                )(conn).declare()

    @staticmethod
    def format_publish_message(
        app, message, exchange, task, id=None, routing_key=""
    ) -> dict:
        header_id = str(id) if id else str(uuid.uuid4())
        return dict(
            exchange=exchange,
            routing_key=routing_key,
            body=message,
            headers=dict(
                task=task,
                id=header_id,
            ),
            content_type="application/json",
        )

    def exchange_queue_binding(self):
        self.app.logger.info("All exchange queue binding")
        for exchange in EXCHANGE_QUEUE_BINDING:
            self.__individual_exchange_queue_binding(exchange)

    def publish_message(self, message, exchange, task, routing_key="", id=None):
        try:
            with self.__get_connection() as conn:
                data = EventPublisher.format_publish_message(
                    app=self.app,
                    message=message,
                    exchange=exchange,
                    task=task,
                    id=id,
                    routing_key=routing_key,
                )
                producer = conn.Producer(serializer="json")
                producer.publish(**data)
                self.app.logger.info(
                    f"Sent message {message} to {exchange} and data is {data}"
                )
        except (ConnectionError, ChannelError) as e:
            self.app.logger.error(
                f"Error {e} on trying to send message {message} to {exchange}"
            )

    def publish_message_to_exchange(
        self, model_instance, task, data,
        exchange, callback_exchange=None, routing_key="", callback_routing_key="",
    ):
        # non model
        message = self.__construct_message_for_non_model_instance(
            model_instance, data, callback_exchange, routing_key, callback_routing_key
        )
        self.publish_message(
            message=message, task=task, exchange=exchange, routing_key=routing_key
        )
