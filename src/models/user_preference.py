from mongoengine import Document
from mongoengine.fields import (
    IntField,
    BooleanField,
    ObjectIdField,
    ListField,
)


class UserPreference(Document):
    user_id = ObjectIdField(required=True)
    is_dark_mode = BooleanField(default=False)
    page_size = IntField(default=5)
    banks_display_order = ListField()
    privacy_mode_enabled = BooleanField(default=False)
