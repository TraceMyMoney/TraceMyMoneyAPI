import pytest, json
from hamcrest import is_, assert_that
from deepdiff import DeepDiff
from bson import ObjectId

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

    def get_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/banks/", headers=headers, params=params, expect_errors=True
        )

    def post_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/banks/create", headers=headers, params=params, expect_errors=True
        )

    def test_get_banks_with_no_data_available_with_incorrect_auth(self, jwt_token):
        response = self.get_banks_api_call(jwt_token)
        assert_that(response.status_code, is_(401))
        assert_that(response.json["error"], is_("User not found"))

    def test_get_banks_with_no_data_available(self):
        response = self.get_banks_api_call(self.api_token)
        assert_that(response.status_code, is_(200))
        assert_that(response.json["banks"], is_([]))

    def test_get_banks_with_data_available(self):
        bank = BankFactory.get_bank(user_id=ObjectId(self.user.id))
        bank.save()
        response = self.get_banks_api_call(self.api_token)
        expected_result = {
            "id": str(bank.id),
            "name": TEST_BANK_NAME,
            "initial_balance": bank.initial_balance,
            "current_balance": bank.current_balance,
            "user_id": str(TEST_USER_ID),
            "total_disbursed_till_now": bank.total_disbursed_till_now,
            "created_at": provide_todays_date(),
            "updated_at": provide_todays_date(),
        }

        assert_that(response.status_code, is_(200))
        for bank in response.json["banks"]:
            assert_that(DeepDiff(expected_result, bank), is_({}))

    def test_get_banks_with_name(self):
        bank = BankFactory.get_bank(user_id=ObjectId(self.user.id))
        bank.save()
        response = self.get_banks_api_call(
            self.api_token, params={"name": TEST_BANK_NAME}
        )
        expected_result = {
            "id": str(bank.id),
            "name": bank.name,
            "initial_balance": bank.initial_balance,
            "current_balance": bank.current_balance,
            "user_id": str(bank.user_id),
            "total_disbursed_till_now": bank.total_disbursed_till_now,
            "created_at": provide_todays_date(),
            "updated_at": provide_todays_date(),
        }

        assert_that(response.status_code, is_(200))
        for bank in response.json["banks"]:
            assert_that(DeepDiff(expected_result, bank), is_({}))

    def test_get_banks_with_id(self):
        bank = BankFactory.get_bank(user_id=ObjectId(self.user.id))
        bank.save()
        response = self.get_banks_api_call(self.api_token, params={"id": str(bank.id)})
        expected_result = {
            "id": str(bank.id),
            "name": TEST_BANK_NAME,
            "initial_balance": bank.initial_balance,
            "current_balance": bank.current_balance,
            "user_id": str(TEST_USER_ID),
            "total_disbursed_till_now": bank.total_disbursed_till_now,
            "created_at": provide_todays_date(),
            "updated_at": provide_todays_date(),
        }

        assert_that(response.status_code, is_(200))
        for bank in response.json["banks"]:
            assert_that(DeepDiff(expected_result, bank), is_({}))

    def test_create_bank_without_created_at(self):
        data = {
            "name": "TestBank1",
            "initial_balance": 10000,
            "current_balance": 10000,
            "total_disbursed_till_now": 0,
        }
        response = self.post_banks_api_call(self.api_token, params=json.dumps(data))
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
        response = self.post_banks_api_call(self.api_token, params=json.dumps(data))
        assert_that(response.status_code, is_(200))
        assert_that(response.json["success"], is_("Bank object saved successfully"))

    def test_create_bank_without_any_fields(self):
        data = {}
        response = self.post_banks_api_call(self.api_token, params=json.dumps(data))
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

    # TODO: write the test case for delting the bank
