from mongoengine import *
from datetime import datetime


class ExpenseEntry(EmbeddedDocument):
    amount = FloatField()
    description = StringField()
    expense_entry_type = StringField()
    ee_id = SequenceField(primary_key=False)
    entry_tags = ListField(StringField())
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())


class Expense(Document):
    day = StringField()
    expenses = EmbeddedDocumentListField(ExpenseEntry)
    bank = LazyReferenceField("Bank", reverse_delete_rule=DENY)
    bank_name = StringField()
    expense_total = FloatField()
    remaining_amount_till_now = FloatField()
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
    user_id = ObjectIdField()
