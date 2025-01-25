import pytest, json
from hamcrest import is_, assert_that
from datetime import datetime, timedelta

# src imports
from src.helpers.helper import provide_todays_date

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.functional.helper.helper import ExpenseHelper, BanksHelper


class TestBankBP:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.expense_helper = ExpenseHelper(testapp)
        self.banks_helper = BanksHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def test_delete_the_bank_without_any_expenses(self):
        # Once we delete the bank, all its expenses, entry tags, etc will be deleted
        bank = BankFactory.get_bank(self.user.id)
        bank.save()
        response = self.banks_helper.delete_banks_api_call(self.api_token, str(bank.id))
        assert_that(response.status_code, is_(204))

    def test_delete_the_bank_with_expenses(self):
        # Once we delete the bank, all its expenses, entry tags, etc will be deleted
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        # create fake expenses
        for i in range(25):
            expense_payload = {
                "bank_id": str(bank.id),
                "created_at": provide_todays_date(
                    datetime.now() + timedelta(days=(0 - i))
                ),
                "expenses": [
                    {"amount": 20, "description": "Test Expense Entry Desription"},
                ],
            }
            _ = self.expense_helper.create_expense_api(
                self.api_token, params=json.dumps(expense_payload)
            )

        banks_response = self.banks_helper.get_banks_api_call(
            self.api_token, params={"id": str(bank.id)}
        )

        assert_that(
            banks_response.json["banks"][0]["total_disbursed_till_now"], is_(20 * 25)
        )  # as there are 25 expenses per 20 total

        delete_banks_response = self.banks_helper.delete_banks_api_call(
            self.api_token, str(bank.id)
        )
        assert_that(delete_banks_response.status_code, is_(204))

        # try to fetch bank after it is deleted
        banks_response = self.banks_helper.get_banks_api_call(
            self.api_token, params={"id": str(bank.id)}
        )
        # we didn't get the banks
        assert_that(banks_response.status_code, is_(200))
        assert_that(banks_response.json["banks"], is_([]))

        # try to delete the bank with the same id again
        delete_banks_response = self.banks_helper.delete_banks_api_call(
            self.api_token, str(bank.id)
        )
        assert_that(delete_banks_response.status_code, is_(400))
        assert_that(
            delete_banks_response.json["error"], is_("Bank not found with provided ID")
        )

        # Try fetching expenses, should get empty
        expense_res = self.expense_helper.get_expenses_api_call(
            self.api_token, {"bank_id": str(bank.id)}
        )
        assert_that(expense_res.status_code, is_(200))
        assert_that(
            expense_res.json["expenses"],
            is_([{"total_expenses": 0}, {"total_summation": 0}]),
        )
