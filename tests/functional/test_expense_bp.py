import pytest, json
from hamcrest import is_, assert_that
from deepdiff import DeepDiff
from bson import ObjectId

# src imports
from src.helpers.helper import provide_todays_date
from src.models.expense import Expense

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.constants import TEST_USER_ID, TEST_BANK_ID, TEST_BANK_NAME


# TODO: setup the mocker for the celery worker


class TestExpenseBP:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def create_expense_api(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/expenses/create", headers=headers, params=params, expect_errors=True
        )

    def test_create_and_verify_expense(self):
        # Create the bank
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        # Create the expense payload
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"}
            ],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        # as the expense is created, we need to cross check the whether the bank has deducted the balance or not
        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(100.0))
        assert_that(expense.bank.id, is_(ObjectId(bank.id)))
        assert_that(expense.bank_name, is_(TEST_BANK_NAME))

        # Here, as this expense is top w.r.t. datewise, hence,
        # expense's remaining_amount_till_now and bank's current_balance must be equal
        # assert_that(expense.remaining_amount_till_now, is_(expense_bank.current_balance))

    def test_create_expense_with_empty_expenses_and_verify_expense(self):
        # Create the bank
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        # Create the expense payload
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(
            response.json["error"],
            is_(
                "Atleast one expense entry should be present while creating the expense"
            ),
        )

    def test_create_expense_with_not_existing_bank(self):
        # Create the expense payload
        expense_payload = {
            "bank_id": str(ObjectId()),
            "created_at": provide_todays_date(),
            "expenses": [],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(
            response.json["error"],
            is_("bank not found for the corresponding id"),
        )

    def test_create_expense_with_not_providing_bank_id(self):
        # Create the expense payload
        expense_payload = {
            "created_at": provide_todays_date(),
            "expenses": [],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(
            response.json["error"],
            is_("please provide bank_id"),
        )
