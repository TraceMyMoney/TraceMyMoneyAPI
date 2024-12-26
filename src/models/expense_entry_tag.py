from mongoengine import Document, StringField, ObjectIdField


class ExpenseEntryTag(Document):
    name = StringField()
    user_id = ObjectIdField()
