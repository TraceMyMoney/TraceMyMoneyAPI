from functools import wraps
from datetime import datetime
from flask_celeryext import AppContextTask

from src.celery.async_task import (
    AsyncTask,
    AsyncTaskMethods,
    AsyncTaskType,
    AsyncTaskStatus,
)
from src.extensions import config


def events_task_initializer(celery_app):
    def decorator(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            self.app = celery_app
            async_task = AsyncTaskMethods.get_record_with_(task_id=self.request.id)
            if async_task:
                self.async_task_obj = async_task
            else:
                self.async_task_obj = AsyncTask(
                    task_id=self.request.id,
                    task_type=AsyncTaskType(kwargs["model"]),
                    payload=kwargs,
                )
            self.async_task_obj.task_status = AsyncTaskStatus.IN_PROGRESS
            self.async_task_obj.status_message += "PROCESSING INITIATED;"
            self.async_task_obj.save()
            return fn(self, *args, **kwargs)
        return wrapper
    return decorator


def periodic_task_initializer(task_type):
    """Instantiate a logger at the decorated class instance level."""

    def task_init(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            self.config = config
            # TODO: uncomment this later
            # self.logger.info("celery worker started")
            # self.logger.info(f"Received args in periodic task initializer - {args}")
            # self.logger.info(f"Received kwargs in periodic task initializer - {kwargs}")
            # self.logger.info("Inside task: {} {}".format(fn.__name__, self.request.id))

            return fn(self, *args, **kwargs)

        return wrapper

    return task_init


class CeleryGenericBaseTask(AppContextTask):
    def on_success(self, retval, task_id, args, kwargs):
        """Success handler.

        Run by the worker if the task executes successfully.

        Arguments:
            retval(Any): The return value of the task.
            task_id(str): Unique id of the executed task.
            args(Tuple): Original arguments for the executed task.
            kwargs(Dict): Original keyword arguments for the executed task.

        Returns:
            None: The return value of this handler is ignored.
        """
        with self.app.flask_app.app_context():
            if hasattr(self, "async_task_obj"):
                self.async_task_obj.task_status = AsyncTaskStatus.DONE
                self.async_task_obj.status_message += ";PROCESSING COMPLETED"
                self.async_task_obj.updated = datetime.utcnow()
                # self.logger.info("task completed")
                self.async_task_obj.save()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Error handler.

        This is run by the worker when the task fails.

        Arguments:
            exc(Exception): The exception raised by the task.
            task_id(str): Unique id of the failed task.
            args(Tuple): Original arguments for the task that failed.
            kwargs(Dict): Original keyword arguments for the task that failed.
            einfo(~billiard.einfo.ExceptionInfo): Exception information.

        Returns:
            None: The return value of this handler is ignored.
        """
        with self.app.flask_app.app_context():
            if hasattr(self, "async_task_obj"):
                self.async_task_obj.task_status = AsyncTaskStatus.EXCEPTION
                self.async_task_obj.status_message += "{};".format(str(exc))
                self.async_task_obj.updated = datetime.utcnow()
                self.async_task_obj.save()

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Handler called after the task returns.

        Arguments:
            status(str): Current task state.
            retval(Any): Task return value/exception.
            task_id(str): Unique id of the task.
            args(Tuple): Original arguments for the task.
            kwargs(Dict): Original keyword arguments for the task.
            einfo(~billiard.einfo.ExceptionInfo): Exception information.

        Returns:
            None: The return value of this handler is ignored.
        """
        pass
