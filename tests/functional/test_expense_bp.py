import pytest, json
from hamcrest import is_, assert_that
from deepdiff import DeepDiff
from bson import ObjectId
from datetime import datetime, timedelta

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

    def create_expense_entry_api(self, api_token, expense_id, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.patch(
            f"/expenses/add-entry?id={expense_id}",
            headers=headers,
            params=params,
            expect_errors=True,
        )

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
            is_("Bank not found for the corresponding id"),
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
            is_("Please provide bank_id"),
        )

    def test_create_expense_for_same_day(self):
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

        # Creating the first expense which gets created successfully
        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        # Creating the same expense which is indicating the same day and it should return the eror
        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(
            response.json["error"],
            is_("You cannot replicate the expense for the same day"),
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
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )
        assert_that(expense_bank.total_disbursed_till_now, is_(expense.expense_total))

    def test_create_multiple_expenses_in_straight_way(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        """
        We have saved the bank object with the total amount of the 1000.
        Now, we will create 3 expense objects with atleast one expense_entry inside it.

        current bank account : 1000

        expense current_day ~ 2:
            - entry 1 => 100
            - entry 2 => 200

            expense total => 300,
            and bank remaining => 1000 - 300 = 700

        expense current_day ~ 1:
            - entry 1 => 50

            expense total => 50,
            and bank remaining => 700 - 50 => 650

        expense current_day:
            - entry 1 => 100
            - entry 2 => 400

            expense total => 500,
            and bank remaining => 650 - 500 => 150

        current bank account : 150
        """

        # current_day ~ 2
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-2)),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response_1 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        assert_that(response_1.status_code, is_(201))
        assert_that(response_1.json["success"], is_("Docuement created successfully"))

        expense_id = response_1.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(300.0))  # 100 + 200
        assert_that(expense.remaining_amount_till_now, is_(700.0))  # 1000 - 300
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        # current_day ~ 1
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-1)),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_2 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        assert_that(response_2.status_code, is_(201))
        assert_that(response_2.json["success"], is_("Docuement created successfully"))

        expense_id = response_2.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(50.0))
        assert_that(expense.remaining_amount_till_now, is_(650.0))  # 700 - 50
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        # current_day
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 400, "description": "Test Expense Entry Desription"},
            ],
        }

        response_3 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        assert_that(response_3.status_code, is_(201))
        assert_that(response_3.json["success"], is_("Docuement created successfully"))

        expense_id = response_3.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(500.0))
        assert_that(expense.remaining_amount_till_now, is_(150.0))  # 650 - 500
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        # finally check the bank's balance
        assert_that(expense_bank.current_balance, is_(150.0))  # 650 - 500

    def test_create_expense_in_middle_way(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        """
        For this test case, let's say we have the 5 expenses as below

            -> expense at (current_day)
            -> expense at (current_day - 1)
            -> expense at (current_day - 2)
            -> < Missing expense at (current_day - 3) >
            -> expense at (current_day - 4)


        current bank account : 1000

        expense current_day ~ 4:
            - entry 1 => 100
            - entry 2 => 200

            expense total => 300,
            and bank remaining => 1000 - 300 = 700

        expense current_day ~ 2:
            - entry 1 => 50

            expense total => 50,
            and bank remaining => 700 - 50 => 650

        expense current_day ~ 1:
            - entry 1 => 100
            - entry 2 => 100

            expense total => 200,
            and bank remaining => 650 - 200 => 450

        expense current_day:
            - entry 1 => 100
            - entry 2 => 50

            expense total => 150,
            and bank remaining => 450 - 150 => 300


        current bank account : 150
        """

        # ----------------------------------------------------------
        # current_day ~ 4
        expense_payload_4 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-4)),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response_4 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_4)
        )

        # ----------------------------------------------------------
        # current_day ~ 2
        expense_payload_2 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-2)),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_2 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_2)
        )

        # ----------------------------------------------------------
        # current_day ~ 1
        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-1)),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 100, "description": "Test Expense Entry Desription"},
            ],
        }

        response_1 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )

        # ----------------------------------------------------------
        # current_day
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 100, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(150.0))
        assert_that(expense.remaining_amount_till_now, is_(300.0))
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        # finally check the bank's balance
        assert_that(expense_bank.current_balance, is_(300.0))

        """
        Now, as we can see, expense at (current_day - 3) is missing and let's add it now.

        expense current_day ~ 3:
            - entry 1 => 10
            - entry 2 => 105

            expense total => 115,

        Here the things get intresting, at (current_day ~ 4) is the prev day for the (current_day ~ 3)
        Hence, we need to check what was the balance for that prev day, and then we need subtract
        3rd expense_total dw, that logic has been written there !

        Hence, on (current_day ~ 4)'s day, the remaining bank's balance was 700,
        thus, on (current_day ~ 3)'s the remaining bank's balance should be  700 - 115 => 585
        But today's bank's balance would be subtracted from the current one only.
        which is 300 - 115
        """

        # current_day ~ 3
        expense_payload_3 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-3)),
            "expenses": [
                {"amount": 10, "description": "Test Expense Entry Desription"},
                {"amount": 105, "description": "Test Expense Entry Desription"},
            ],
        }

        response_3 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_3)
        )

        expense_id = response_3.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(115.0))
        assert_that(expense.remaining_amount_till_now, is_(585.0))

        # finally check the bank's balance
        assert_that(expense_bank.current_balance, is_(185.0))  # 300 - 115

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

        response = self.create_expense_api(
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
        response = self.create_expense_entry_api(
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

    def test_multiple_upper_expenses_via_creating_expense_entries(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        """
        expense 1:
            - expense_total => 400
            - remaining now => 1000 - 400 => 600

        expense 2
            - expense_total => 300
            - remaining now => 600 - 300 => 300
        """

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-1)),
            "expenses": [
                {"amount": 200, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response_1 = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )

        # current_day ~ 1
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 300, "description": "Test Expense Entry Desription"},
            ],
        }

        response = self.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(300.0))
        assert_that(expense.remaining_amount_till_now, is_(300.0))
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        assert_that(expense_bank.current_balance, is_(300))

        """
        Now, let's add the expense entries in the (current_day - 1)'s expense which is 400,
        here, 150 + 100 => 250 got added in the form of expense entries
        hence, total till now is => 400 + 250 => 650
        """

        entry_payload = [
            {
                "amount": 150,
                "description": "from test",
            },
            {
                "amount": 100,
                "description": "from test",
            },
        ]
        expense_1_id = response_1.json["_id"]
        _ = self.create_expense_entry_api(
            self.api_token,
            expense_id=str(expense_1_id),
            params=json.dumps(entry_payload),
        )

        expense = Expense.objects(id=ObjectId(expense_1_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(650.0))  # 400 + 250
        assert_that(expense.remaining_amount_till_now, is_(350.0))

        # final check for bank balance
        assert_that(expense_bank.current_balance, is_(50.0))

        # final check for the consucutive upper expenses as well for remaining_amount_till_now
        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        assert_that(expense.remaining_amount_till_now, is_(50.0))
