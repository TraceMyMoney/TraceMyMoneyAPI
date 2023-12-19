from datetime import datetime
from mongoengine import ( StringField,
                          DateTimeField,
                          EmbeddedDocument,
                          FloatField )

class ExpenseEntry(EmbeddedDocument):
    amount = FloatField()
    description = StringField()
    expense_entry_type = StringField()
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
