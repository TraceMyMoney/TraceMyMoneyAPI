from datetime import datetime
from enum import Enum

from mongoengine import (
    Document,
    StringField,
    EnumField,
    DynamicField,
    IntField,
    DateTimeField,
)
from src.database import BaseMethods


class AsyncTaskType(Enum):
    BUILD_EXCEL_AND_SEND_EMAIL = "build_excel_and_send_email"


class AsyncTaskStatus(Enum):
    PENDING = "PENDING"
    EXCEPTION = "EXCEPTION"
    DONE = "DONE"
    IN_PROGRESS = "IN_PROGRESS"


class AsyncTask(Document):
    task_id = StringField(max_length=64)
    task_type = EnumField(AsyncTaskType, required=True)
    task_status = EnumField(
        AsyncTaskStatus, required=True, default=AsyncTaskStatus.PENDING
    )
    payload = DynamicField()
    status_message = StringField(default="")
    retries = IntField(default=0)
    created = DateTimeField(default=datetime.utcnow)
    updated = DateTimeField(default=datetime.utcnow)
    meta = dict(
        indexes=[
            dict(fields=["task_id"], unique=True, name="index_unique_async_task_id"),
            dict(fields=["task_status"], name="index_async_task_status"),
        ]
    )


class AsyncTaskMethods(BaseMethods):
    model = AsyncTask
