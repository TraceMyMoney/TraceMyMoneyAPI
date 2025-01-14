from bson import ObjectId

# src imports
from src.models.expense_entry_tag import ExpenseEntryTag

# tests imports
from tests.constants import TEST_USER_ID, TEST_EXPENSE_ENTRY_TAG_NAME


class ExpenseEntryTagFactroy:

    @staticmethod
    def get_expense_entry_tag(name=TEST_EXPENSE_ENTRY_TAG_NAME, user_id=TEST_USER_ID):
        return ExpenseEntryTag(name=name, user_id=user_id)
