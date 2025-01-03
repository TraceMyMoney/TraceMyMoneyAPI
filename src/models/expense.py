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

# relative imports
from src.constants import DATE_TIME_FORMAT
from src.models import expense_entry


class Expense(Document):
    day = StringField()
    expenses = EmbeddedDocumentListField(expense_entry.ExpenseEntry)
    bank = LazyReferenceField("Bank", reverse_delete_rule=DENY)
    bank_name = StringField()
    expense_total = FloatField()
    remaining_amount_till_now = FloatField()  # TODO: write the logic for this later !
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())
    user_id = ObjectIdField()

    # Setup the unique indexes
    meta = dict(indexes=[dict(fields=["created_at", "bank"], unique=True)])

    def get_total_of_expenses(self):
        return sum([ee.amount for ee in self.expenses])

    def get_bank(self):
        return self.bank.fetch()  # concept of lazy reference field

    @classmethod
    def get_expenses(cls, current_user, **kwargs):
        # TODO: Make the default page_number and per_page as constants
        page_number = int(kwargs.get("page_number", 1))
        per_page = int(kwargs.get("per_page", 5))
        expenses = cls.objects(
            user_id=current_user.id, bank=ObjectId(kwargs.get("bank_id"))
        )
        total_expenses = expenses.count()
        if kwargs.get("id"):
            expenses = expenses.filter(id=kwargs.get("id"))
        else:
            if kwargs.get("created_at"):
                expenses = expenses.filter(
                    created_at=datetime.strptime(
                        kwargs.get("created_at"), DATE_TIME_FORMAT
                    )
                )
            elif kwargs.get("start_date"):
                dict_ = {
                    "created_at__gte": datetime.strptime(
                        kwargs.get("start_date"), DATE_TIME_FORMAT
                    )
                }
                if kwargs.get("end_date"):
                    dict_["created_at__lte"] = datetime.strptime(
                        kwargs.get("end_date"), DATE_TIME_FORMAT
                    )
                expenses = expenses.filter(**dict_).order_by("created_at")

            if kwargs.get("bank_name"):
                expenses = expenses.filter(bank_name=kwargs.get("bank_name"))

        return expenses.order_by("-created_at")[
            (page_number - 1) * per_page : per_page * page_number
        ], total_expenses
