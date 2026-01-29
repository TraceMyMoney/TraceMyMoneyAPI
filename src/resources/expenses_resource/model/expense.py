from mongoengine import *
from datetime import datetime

from src.models import expense_entry


class Expense(Document):
    day = StringField()
    expenses = EmbeddedDocumentListField(expense_entry.ExpenseEntry)
    bank = LazyReferenceField("Bank", reverse_delete_rule=DENY)
    bank_name = StringField()
    expense_total = FloatField()
    remaining_amount_till_now = FloatField()
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
    user_id = ObjectIdField()
