from mongoengine import (
    Document,
    StringField,
)


class ExpenseEntryTag(Document):
    name = StringField()
