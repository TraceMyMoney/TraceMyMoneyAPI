import pytest, json
from hamcrest import is_, assert_that
from bson import ObjectId

# src imports
from src.helpers.helper import provide_todays_date
from src.models.expense import Expense
from src.models.bank import Bank

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.functional.helper.helper import ExpenseHelper


class TestExpensesModify:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.expense_helper = ExpenseHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def test_update_expense_entry_with_description(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }
        response_1 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )
        expense_id = response_1.json["_id"]

        # by default the ee counter starts from 1
        payload = {
            "expense_id": str(expense_id),
            "entry_id": 1,
            "updated_description": "TEST Update",
        }

        res = self.expense_helper.update_expense_entry_api(
            self.api_token, json.dumps(payload)
        )
        assert_that(res.status_code, is_(201))
        assert_that(res.json["data"], is_(payload))

        expense = Expense.objects(id=expense_id).first()
        expense_entry = expense.expenses[0]
        assert_that(expense_entry.description, is_("TEST Update"))

    def test_update_expense_entry_with_tags(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }
        response_1 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )
        expense_id = response_1.json["_id"]
        fake_select_tag_id = ObjectId()

        # by default the ee counter starts from 1
        payload = {
            "expense_id": str(expense_id),
            "entry_id": 1,
            "selected_tags": [str(fake_select_tag_id)],
        }

        res = self.expense_helper.update_expense_entry_api(
            self.api_token, json.dumps(payload)
        )
        assert_that(res.status_code, is_(201))
        assert_that(res.json["data"], is_(payload))

        expense = Expense.objects(id=expense_id).first()
        expense_entry = expense.expenses[0]
        assert_that(expense_entry.entry_tags[0], is_(str(fake_select_tag_id)))

    def test_update_expense_entry_with_tags_and_description(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }
        response_1 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )
        expense_id = response_1.json["_id"]
        fake_select_tag_id = ObjectId()

        # by default the ee counter starts from 1
        payload = {
            "expense_id": str(expense_id),
            "entry_id": 1,
            "updated_description": "Test Description update",
            "selected_tags": [str(fake_select_tag_id)],
        }

        res = self.expense_helper.update_expense_entry_api(
            self.api_token, json.dumps(payload)
        )
        assert_that(res.status_code, is_(201))
        assert_that(res.json["data"], is_(payload))

        expense = Expense.objects(id=expense_id).first()
        expense_entry = expense.expenses[0]
        assert_that(expense_entry.entry_tags[0], is_(str(fake_select_tag_id)))
        assert_that(expense_entry.description, is_("Test Description update"))
