import pytest, json
from hamcrest import is_, assert_that
from deepdiff import DeepDiff
from bson import ObjectId
from datetime import datetime, timedelta

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

    def __get_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/banks/", headers=headers, params=params, expect_errors=True
        )

    def __get_expenses_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/expenses/", headers=headers, params=params, expect_errors=True
        )

    def __post_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/banks/create", headers=headers, params=params, expect_errors=True
        )

    def __create_expense_api(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/expenses/create", headers=headers, params=params, expect_errors=True
        )

    def __delete_banks_api_call(self, api_token, bank_id):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.delete(
            f"/banks/delete?bank_id={bank_id}",
            headers=headers,
            params={},
            expect_errors=True,
        )

    def test_get_banks_with_no_data_available_with_incorrect_auth(self, jwt_token):
        response = self.__get_banks_api_call(jwt_token)
        assert_that(response.status_code, is_(401))
        assert_that(response.json["error"], is_("User not found"))

    def test_get_banks_with_no_data_available(self):
        response = self.__get_banks_api_call(self.api_token)
        assert_that(response.status_code, is_(200))
        assert_that(response.json["banks"], is_([]))

    def test_get_banks_with_data_available(self):
        bank = BankFactory.get_bank(user_id=ObjectId(self.user.id))
        bank.save()
        response = self.__get_banks_api_call(self.api_token)
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
        response = self.__get_banks_api_call(
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
        response = self.__get_banks_api_call(
            self.api_token, params={"id": str(bank.id)}
        )
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
        response = self.__post_banks_api_call(self.api_token, params=json.dumps(data))
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
        response = self.__post_banks_api_call(self.api_token, params=json.dumps(data))
        assert_that(response.status_code, is_(200))
        assert_that(response.json["success"], is_("Bank object saved successfully"))

    def test_create_bank_without_any_fields(self):
        data = {}
        response = self.__post_banks_api_call(self.api_token, params=json.dumps(data))
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

    def test_delete_the_bank(self):
        # Once we delete the bank, all its expenses, entry tags, etc will be deleted
        bank = BankFactory.get_bank(self.user.id)
        bank.save()
        response = self.__delete_banks_api_call(self.api_token, str(bank.id))
        assert_that(response.status_code, is_(204))

    def test_delete_the_bank(self):
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
            _ = self.__create_expense_api(
                self.api_token, params=json.dumps(expense_payload)
            )

        banks_response = self.__get_banks_api_call(
            self.api_token, params={"id": str(bank.id)}
        )

        assert_that(
            banks_response.json["banks"][0]["total_disbursed_till_now"], is_(20 * 25)
        )  # as there are 25 expenses per 20 total

        delete_banks_response = self.__delete_banks_api_call(
            self.api_token, str(bank.id)
        )
        assert_that(delete_banks_response.status_code, is_(204))

        # try to fetch bank after it is deleted
        banks_response = self.__get_banks_api_call(
            self.api_token, params={"id": str(bank.id)}
        )
        # we didn't get the banks
        assert_that(banks_response.status_code, is_(200))
        assert_that(banks_response.json["banks"], is_([]))

        # try to delete the bank with the same id again
        delete_banks_response = self.__delete_banks_api_call(
            self.api_token, str(bank.id)
        )
        assert_that(delete_banks_response.status_code, is_(400))
        assert_that(
            delete_banks_response.json["error"], is_("Bank not found with provided ID")
        )

        # Try fetching expenses, should get empty
        expense_res = self.__get_expenses_api_call(
            self.api_token, {"bank_id": str(bank.id)}
        )
        assert_that(expense_res.status_code, is_(200))
        assert_that(
            expense_res.json["expenses"],
            is_([{"total_expenses": 0}, {"total_summation": 0}]),
        )
