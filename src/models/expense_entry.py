from datetime import datetime
from mongoengine import ( StringField,
                          DateTimeField,
                          EmbeddedDocument,
                          FloatField,
                          SequenceField )

class ExpenseEntry(EmbeddedDocument):
    amount = FloatField()
    description = StringField()
    expense_entry_type = StringField()
    ee_id = SequenceField(primary_key=False)
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
