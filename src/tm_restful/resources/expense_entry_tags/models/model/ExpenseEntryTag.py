from mongoengine import Document, StringField, ObjectIdField


class ExpenseEntryTag(Document):
    name = StringField()
    user_id = ObjectIdField()

    @classmethod
    def get_tags(cls, current_user, **data):
        query = {"user_id": current_user.id}
        if data.get("name"):
            query["name"] = (
                {"$regex": data["name"]} if data.get("regex") else data["name"]
            )
        elif data.get("id"):
            query["id"] = data["id"]

        return list(
            map(
                lambda tag_object: {"id": str(tag_object.id), "name": tag_object.name},
                ExpenseEntryTag.objects(**query),
            )
        )

    @classmethod
    def is_entry_exists(cls, name):
        return True if cls.objects(name=name).first() else False
