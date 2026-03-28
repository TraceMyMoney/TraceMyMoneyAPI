from src.models.bank import Bank
from src.database import BaseMethods
from src.resources.expense_entry_tags_resource.model.expense_entry_tag import ExpenseEntryTag


class ExpenseEntryTagDBMethods(BaseMethods):
    model = ExpenseEntryTag

    @classmethod
    def get_tags(cls, current_user, **data):
        query = {"user_id": current_user.id}
        if data.get("name"):
            query["name"] = {"$regex": data["name"]} if data.get("regex") else data["name"]
        elif data.get("id"):
            query["id"] = data["id"]

        return list(
            map(
                lambda tag_object: {"id": str(tag_object.id), "name": tag_object.name},
                cls.model.objects(**query),
            )
        )
