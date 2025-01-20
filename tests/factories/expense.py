# src imports
from src.models.expense import Expense
from src.models.expense_entry import ExpenseEntry

# tests imports
from tests.constants import TEST_USER_ID, TEST_BANK_ID, TEST_BANK_NAME, TEST_DESCRIPTION


class ExpenseFactory:

    @staticmethod
    def get_expense(
        day="Monday",
        expenses=[
            ExpenseEntry(
                **{
                    "amount": 100,
                    "description": TEST_DESCRIPTION,
                    "expense_entry_type": None,
                    "entry_tags": [],
                }
            )
        ],
        bank=TEST_BANK_ID,
        bank_name=TEST_BANK_NAME,
        expense_total=100,
        remaining_amount_till_now=900,
        user_id=TEST_USER_ID,
    ):
        return Expense(
            day=day,
            expenses=expenses,
            bank=bank,
            bank_name=bank_name,
            expense_total=expense_total,
            remaining_amount_till_now=remaining_amount_till_now,
            user_id=user_id,
        )
