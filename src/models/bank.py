# libraries imports
from datetime import datetime
from mongoengine import (
    Document,
    StringField,
    FloatField,
    DateTimeField,
    ObjectIdField,
)

# relative imports
from src.helpers import helper


class Bank(Document):
    name = StringField(max_length=20, required=True)
    initial_balance = FloatField(required=True)
    current_balance = FloatField(required=True)
    user_id = ObjectIdField(required=True)
    total_disbursed_till_now = FloatField(required=True)
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())

    def __str__(self):
        return f"<Bank:{self.name}>"

    @classmethod
    def get_banks(cls, current_user, **kwargs):
        banks = cls.objects(user_id=current_user.id)
        if kwargs.get("name"):
            banks = banks.filter(name=kwargs["name"])
        if kwargs.get("id"):
            banks = banks.filter(id=kwargs["id"])

        return banks

    def update_bank_data_after_expense_deletion(self, expense):
        if ee_total := expense.expense_total:
            current_balalnce = self.current_balance + ee_total
            total_disbursed_till_now = self.total_disbursed_till_now - ee_total
            self.update(
                set__total_disbursed_till_now=total_disbursed_till_now,
                set__current_balance=current_balalnce,
            )
            self.reload()
