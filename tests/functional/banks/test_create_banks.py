import pytest, json
from hamcrest import is_, assert_that

# src imports
from src.helpers.helper import provide_todays_date

# tests imports
from tests.factories.user import UserFactory
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

    def test_create_bank_without_created_at(self):
        data = {
            "name": "TestBank1",
            "initial_balance": 10000,
            "current_balance": 10000,
            "total_disbursed_till_now": 0,
        }
        response = self.banks_helper.post_banks_api_call(
            self.api_token, params=json.dumps(data)
        )
        assert_that(response.status_code, is_(200))
        assert_that(response.json["success"], is_("Bank object saved successfully"))

    def test_create_bank_with_created_at(self):
        data = {
            "name": "TestBank1",
            "initial_balance": 10000,
            "current_balance": 10000,
            "total_disbursed_till_now": 0,
            "created_at": provide_todays_date(),
        }
        response = self.banks_helper.post_banks_api_call(
            self.api_token, params=json.dumps(data)
        )
        assert_that(response.status_code, is_(200))
        assert_that(response.json["success"], is_("Bank object saved successfully"))

    def test_create_bank_without_any_fields(self):
        data = {}
        response = self.banks_helper.post_banks_api_call(
            self.api_token, params=json.dumps(data)
        )
        assert_that(response.status_code, is_(400))
        required_fields = [
            "name",
            "initial_balance",
            "current_balance",
            "total_disbursed_till_now",
        ]
        for item, index in zip(response.json["error"], range(0, len(required_fields))):
            assert_that(item[0], is_(required_fields[index]))
            assert_that(item[1], is_("Field is required"))
