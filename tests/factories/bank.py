from bson import ObjectId

# src imports
from src.models.bank import Bank

# test imports
from tests.constants import TEST_USER_ID, TEST_BANK_NAME


class BankFactory:

    @staticmethod
    def get_bank(
        name=TEST_BANK_NAME,
        initial_balance=1000,
        current_balance=1000,
        total_disbursed_till_now=0,
        user_id=TEST_USER_ID,
    ):
        return Bank(
            name=name,
            initial_balance=initial_balance,
            current_balance=current_balance,
            total_disbursed_till_now=total_disbursed_till_now,
            user_id=user_id,
        )
