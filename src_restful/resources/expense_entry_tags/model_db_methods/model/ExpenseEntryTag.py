from mongoengine import Document, StringField, ObjectIdField


class ExpenseEntryTag(Document):
    name = StringField()
    user_id = ObjectIdField()

    @classmethod
    def is_entry_exists(cls, name):
        return True if cls.objects(name=name).first() else False
