import pytest, datetime
from hamcrest import is_, assert_that
from deepdiff import DeepDiff

# src imports
from src.helpers.helper import provide_todays_date

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.constants import TEST_USER_ID, TEST_BANK_ID, TEST_BANK_NAME


class TestBankBP:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def make_get_bank_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/banks/", headers=headers, params=params, expect_errors=True
        )

    def test_get_banks_with_no_data_available_incorrect_auth(self, jwt_token):
        response = self.make_get_bank_api_call(jwt_token)
        assert_that(response.status_code, is_(401))
        assert_that(response.json["error"], is_("User not found"))

    def test_get_banks_with_no_data_available(self):
        response = self.make_get_bank_api_call(self.api_token)
        assert_that(response.status_code, is_(200))
        assert_that(response.json["banks"], is_([]))

    def test_get_banks_with_data_available(self):
        bank = BankFactory.get_bank()
        bank.save()
        response = self.make_get_bank_api_call(self.api_token)
        assert_that(response.status_code, is_(200))

        expected_result = {
            "_id": TEST_BANK_ID,
            "name": TEST_BANK_NAME,
            "initial_balance": 1000.0,
            "current_balance": 1000.0,
            "user_id": TEST_USER_ID,
            "total_disbursed_till_now": 0.0,
            "created_at": provide_todays_date(),
            "updated_at": provide_todays_date(),
        }
        for bank in response.json["banks"]:
            assert_that(DeepDiff(expected_result, bank))
