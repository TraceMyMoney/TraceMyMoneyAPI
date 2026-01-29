from src.models.bank import Bank
from src.database import BaseMethods


class BankDBMethods(BaseMethods):
    model = Bank

    @classmethod
    def get_banks(cls, current_user, **kwargs):
        banks = cls.model.objects(user_id=current_user.id)
        if kwargs.get("name"):
            banks = banks.filter(name=kwargs["name"])
        if kwargs.get("id"):
            banks = banks.filter(id=kwargs["id"])

        return banks

    @classmethod
    def update_bank_data_after_expense_deletion(self, expense):
        if ee_total := expense.expense_total:
            current_balance = self.current_balance + ee_total
            total_disbursed_till_now = self.total_disbursed_till_now - ee_total
            self.update(
                set__total_disbursed_till_now=total_disbursed_till_now,
                set__current_balance=current_balance,
            )
            self.reload()
