import pytest, json, random
from hamcrest import is_, assert_that
from bson import ObjectId
from datetime import datetime, timedelta

# src imports
from src.helpers.helper import provide_todays_date
from src.models.expense import Expense

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.functional.helper.helper import ExpenseHelper
from tests.constants import TEST_BANK_NAME


class TestExpensesCreate:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.expense_helper = ExpenseHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()


    def test_expenses_via_creating_expense_entries(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()
        expense_payload_4 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-4)),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_4)
        )

        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(300.0))
        assert_that(expense.remaining_amount_till_now, is_(700.0))
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )
        assert_that(expense_bank.current_balance, is_(700.0))

        # Now, we try adding the expense entries in the current expense
        entry_payload = [
            {
                "amount": 300,
                "description": "from test",
            },
            {
                "amount": 100,
                "description": "from test",
            },
        ]
        response = self.expense_helper.create_expense_entry_api(
            self.api_token, expense_id=str(expense_id), params=json.dumps(entry_payload)
        )

        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(700.0))
        assert_that(expense.remaining_amount_till_now, is_(300.0))
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )
        assert_that(expense_bank.current_balance, is_(300.0))
