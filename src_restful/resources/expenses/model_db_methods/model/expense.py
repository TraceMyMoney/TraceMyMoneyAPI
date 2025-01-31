# libraries imports
from datetime import datetime
from bson import ObjectId
from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    EmbeddedDocumentListField,
    LazyReferenceField,
    FloatField,
    ObjectIdField,
    DENY,
)
from functools import reduce

# relative imports
from src_restful.constants import DATE_TIME_FORMAT
from src.models import expense_entry


class Expense(Document):
    day = StringField()
    expenses = EmbeddedDocumentListField(expense_entry.ExpenseEntry)
    bank = LazyReferenceField("Bank", reverse_delete_rule=DENY)
    bank_name = StringField()
    expense_total = FloatField()
    remaining_amount_till_now = FloatField()
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
    user_id = ObjectIdField()

    def get_total_of_expenses(self):
        return sum([ee.amount for ee in self.expenses])

    def get_bank(self):
        return self.bank.fetch()  # concept of lazy reference field

    @classmethod
    def get_expenses(cls, current_user, **kwargs):
        # TODO: Make the default page_number and per_page as constants
        page_number = int(kwargs.get("page_number", 1))
        per_page = int(kwargs.get("per_page", 5))
        search_matcher = {}
        search_with_operator = [{"user_id": current_user.id}]
        if kwargs.get("advanced_search", False):
            if search_by_tags := kwargs.get("search_by_tags"):
                search_with_operator.append(
                    {"expenses.entry_tags": {"$in": search_by_tags}}
                )
            if search_by_keyword := kwargs.get("search_by_keyword"):
                search_with_operator.append(
                    {
                        "expenses.description": {
                            "$regex": search_by_keyword,
                            "$options": "i",
                        }
                    }
                )
            if search_by_bank_ids := kwargs.get("search_by_bank_ids"):
                objectified_bank_ids = list(
                    map(lambda x: ObjectId(x), search_by_bank_ids)
                )
                search_with_operator.append(
                    {"bank": {"$in": objectified_bank_ids}},
                )
            if search_by_daterange := kwargs.get("search_by_daterange"):
                objectified_daterange = {
                    "created_at": {
                        "$gte": datetime.strptime(
                            search_by_daterange["start_date"], DATE_TIME_FORMAT
                        )
                    }
                }
                if search_by_daterange.get("end_date"):
                    objectified_daterange["created_at"]["$lte"] = datetime.strptime(
                        search_by_daterange["end_date"], DATE_TIME_FORMAT
                    )
                search_with_operator.append(objectified_daterange)
        else:
            search_with_operator.append({"bank": ObjectId(kwargs.get("bank_id"))})

        search_matcher = {f"${kwargs.get('operator', 'and')}": search_with_operator}
        expenses = list(
            cls.objects.aggregate(
                [
                    {"$match": search_matcher},
                    {"$unwind": "$expenses"},
                    {"$match": search_matcher},
                    {
                        "$group": {
                            "_id": "$_id",
                            "id": {"$first": "$_id"},
                            "created_at": {"$first": "$created_at"},
                            "day": {"$first": "$day"},
                            "expense_total": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": ["$expenses.amount", 0]},
                                        "$expenses.amount",
                                        0,
                                    ]
                                }
                            },
                            "topup_expense_total": {
                                "$sum": {
                                    "$cond": [
                                        {"$lt": ["$expenses.amount", 0]},
                                        "$expenses.amount",
                                        0,
                                    ]
                                }
                            },
                            "remaining_amount_till_now": {
                                "$first": "$remaining_amount_till_now"
                            },
                            "user_id": {"$first": "$user_id"},
                            "bank_name": {"$first": "$bank_name"},
                            "expenses": {"$push": "$expenses"},
                        }
                    },
                    {"$sort": {"created_at": -1}},
                ]
            )
        )
        paginated_expenses = expenses[
            (page_number - 1) * per_page : per_page * page_number
        ]
        return (
            paginated_expenses,
            len(expenses),
            reduce(
                lambda total, doc: total + doc["expense_total"], paginated_expenses, 0
            ),
            reduce(
                lambda total, doc: total + doc["topup_expense_total"],
                paginated_expenses,
                0,
            ),
        )
