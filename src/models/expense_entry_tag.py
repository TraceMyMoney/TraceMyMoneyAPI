from mongoengine import Document, StringField, ObjectIdField


class ExpenseEntryTag(Document):
    name = StringField(unique=True)
    user_id = ObjectIdField()

    