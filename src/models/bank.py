from datetime import datetime
from mongoengine import ( Document,
                          StringField,
                          FloatField,
                          DateTimeField,
                          ListField,
                          LazyReferenceField )

class Bank(Document):
    name = StringField(max_length=20)
    initial_balance = FloatField()
    current_balance = FloatField()
    remaining_balance = FloatField()
    expenses = ListField(LazyReferenceField('Expense'))
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())

    def __repr__(self):
        return f'<Bank:{self.name}>'

    def get_expenses(self):
        return self.expenses.fetch()
