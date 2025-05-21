from mongoengine import Document, StringField, EmailField, BooleanField


class User(Document):
    username = StringField(max_length=20, min_length=7)
    email = EmailField()
    password = StringField()
    is_subscribed_to_emails = BooleanField(default=True)
