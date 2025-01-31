from src_restful.resources.expense_entry_tags.models.model.ExpenseEntryTag import (
    ExpenseEntryTag,
)
from src_restful.utils.exception import (
    ValueErrorWithoutNotification,
)


class ExpenseEntryDBMethods:

    def get_tags(self, current_user, **data):
        query = {"user_id": current_user.id}
        if data.get("_id"):
            query["id"] = data["_id"]
        elif data.get("name"):
            query["name"] = (
                {"$regex": data["name"]} if data.get("regex") else data["name"]
            )
        else:
            pass
        return ExpenseEntryTag.objects(**query).all()

    def create_tags(self, current_user, **data):
        query = {"name": data["name"], "user_id": current_user.id}
        entry_tag = ExpenseEntryTag(**query)
        entry_tag.save()
        return entry_tag.id

    def delete_tag(self, current_user, **data):
        query = {"user_id": current_user.id, "id": data.get("_id")}
        if entry_tag := ExpenseEntryTag.objects(**query).first():
            return True if not entry_tag.delete() else False
        else:
            raise ValueErrorWithoutNotification("Tag not found")
