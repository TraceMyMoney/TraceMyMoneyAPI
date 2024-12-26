from mongoengine import signals
from werkzeug.security import generate_password_hash


from src.models.user import User


def pre_save_user(sender, document, **kwargs):
    document.password = generate_password_hash(document.password)
    return document


signals.pre_save.connect(pre_save_user, sender=User)
