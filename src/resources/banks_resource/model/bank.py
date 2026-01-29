from datetime import datetime
from mongoengine import Document, StringField, FloatField, DateTimeField, ObjectIdField


class Bank(Document):
    name = StringField(max_length=20, required=True)
    initial_balance = FloatField(required=True)
    current_balance = FloatField(required=True)
    user_id = ObjectIdField(required=True)
    total_disbursed_till_now = FloatField(required=True)
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())

    def __str__(self):
        return f"<Bank:{self.name}>"
