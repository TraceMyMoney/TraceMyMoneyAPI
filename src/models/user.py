from mongoengine import Document, StringField, EmailField


class User(Document):
    username = StringField(max_length=20, min_length=7)
    email = EmailField()
    password = StringField()
