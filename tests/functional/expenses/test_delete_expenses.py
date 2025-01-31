import pytest, json, random
from hamcrest import is_, assert_that
from bson import ObjectId
from datetime import datetime, timedelta

# src imports
from src.helpers.helper import provide_todays_date
from src.models.expense import Expense
from src.models.bank import Bank

# tests imports
from tests.factories.user import UserFactory
from tests.factories.bank import BankFactory
from tests.functional.helper.helper import ExpenseHelper


class TestExpensesDelete:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.expense_helper = ExpenseHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def test_delete_expense(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        """'
        bank balance => 1000

        expense =>
            - expense total => 350
            - bank's remaining now => 650

        Now, if expense deleted =>
            - bank balance => 650 +  350 => 1000
        """

        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 150, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )

        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        expense_id = response.json["_id"]
        expense = Expense.objects(id=ObjectId(expense_id)).first()
        expense_bank = expense.get_bank()
        assert_that(expense.expense_total, is_(350.0))
        assert_that(expense.remaining_amount_till_now, is_(650.0))
        assert_that(
            expense_bank.current_balance, is_(expense.remaining_amount_till_now)
        )

        assert_that(expense_bank.current_balance, is_(650))

        # Here, delete the expense.
        delete_response = self.expense_helper.delete_expense_api(
            self.api_token, str(expense_id)
        )
        assert_that(delete_response.status_code, is_(204))  # No content

        # Finally check the bank balance, which should be inctemented by expense total
        bank = Bank.objects(id=ObjectId(bank.id)).first()
        assert_that(bank.current_balance, is_(1000))

    def test_delete_expense_if_not_expense_id_provided(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 150, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        _ = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        delete_response = self.expense_helper.delete_expense_api(
            self.api_token, str(ObjectId())
        )
        assert_that(delete_response.status_code, is_(404))
        assert_that(delete_response.json["error"], is_("Document not found"))

    def test_delete_expense_entry(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 150, "description": "Test Expense Entry Desription"},
                {"amount": 200, "description": "Test Expense Entry Desription"},
            ],
        }

        response = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))

        expense_id = response.json["_id"]
        expense = Expense.objects(id=expense_id).first()
        earlier_expense_total = expense.expense_total
        earlier_remaining_amount = expense.remaining_amount_till_now
        ee_map = {doc.ee_id: doc.amount for doc in expense.expenses}
        ee_id = random.choice(list(ee_map.keys()))  # select random ee_id

        response = self.expense_helper.delete_expense_entry_api(
            self.api_token, str(expense_id), ee_id
        )
        assert_that(response.status_code, is_(204))  # No content

        # fetching the expense again
        expense = Expense.objects(id=expense_id).first()
        assert_that(expense.expense_total, is_(earlier_expense_total - ee_map[ee_id]))
        assert_that(
            expense.remaining_amount_till_now,
            is_(earlier_remaining_amount + ee_map[ee_id]),
        )

        # checking the bank's balance, should have been increamented by the amount of deleted entry
        expense_bank = expense.get_bank()
        assert_that(
            expense_bank.current_balance, is_(earlier_remaining_amount + ee_map[ee_id])
        )

    def test_delete_expense_from_middle_of_multiple_expenses(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-3)),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_1 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )
        assert_that(response_1.status_code, is_(201))
        assert_that(response_1.json["success"], is_("Docuement created successfully"))

        expense_payload_2 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-2)),
            "expenses": [
                {"amount": 150, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_2 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_2)
        )
        assert_that(response_2.status_code, is_(201))
        assert_that(response_2.json["success"], is_("Docuement created successfully"))

        expense_payload_3 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-1)),
            "expenses": [
                {"amount": 60, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_3 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_3)
        )
        assert_that(response_3.status_code, is_(201))
        assert_that(response_3.json["success"], is_("Docuement created successfully"))

        expense_payload_4 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 60, "description": "Test Expense Entry Desription"},
                {"amount": 30, "description": "Test Expense Entry Desription"},
            ],
        }

        response_4 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_4)
        )
        assert_that(response_4.status_code, is_(201))
        assert_that(response_4.json["success"], is_("Docuement created successfully"))

        """
        (splits) ---- (total) ---- (remaining)

        (current_day - 3) =>
            50, 50 ---- 100 ---- 900

        (current_day - 2) =>
            150, 50 ---- 200 ---- 700

        (current_day - 1) =>
            50, 60 ---- 110 ---- 590

        (current_day) =>
            30, 60 ---- 90 ---- 500
        """

        expense_id = response_4.json["_id"]
        expense = Expense.objects(id=expense_id).first()
        bank = expense.get_bank()
        assert_that(expense.remaining_amount_till_now, is_(500))
        assert_that(bank.current_balance, is_(expense.remaining_amount_till_now))

        """
        Now, we will be deleting this expense
        (current_day - 2) => 150, 50 ---- 200 ---- 700

        Hence, upper expenses will be

        (current_day - 1) =>
            50, 60 ---- 110 ---- 590 + 200 = 790

        (current_day) =>
            30, 60 ---- 90 ---- 500 + 200 => 700
        """
        delete_expense_id = response_2.json["_id"]
        delete_response = self.expense_helper.delete_expense_api(
            self.api_token, delete_expense_id
        )
        assert_that(delete_response.status_code, is_(204))

        current_day_1_expense_id = response_3.json["_id"]
        current_day_expense_id = response_4.json["_id"]

        current_day_1_expense = Expense.objects(id=current_day_1_expense_id).first()
        current_day_expense = Expense.objects(id=current_day_expense_id).first()

        assert_that(current_day_1_expense.remaining_amount_till_now, is_(200 + 590))
        assert_that(current_day_expense.remaining_amount_till_now, is_(200 + 500))

    def test_delete_expense_entry_from_middle_of_multiple_expenses(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload_1 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-3)),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_1 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_1)
        )
        assert_that(response_1.status_code, is_(201))
        assert_that(response_1.json["success"], is_("Docuement created successfully"))

        expense_payload_2 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-2)),
            "expenses": [
                {"amount": 150, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_2 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_2)
        )
        assert_that(response_2.status_code, is_(201))
        assert_that(response_2.json["success"], is_("Docuement created successfully"))

        expense_payload_3 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(datetime.now() + timedelta(days=-1)),
            "expenses": [
                {"amount": 60, "description": "Test Expense Entry Desription"},
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }

        response_3 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_3)
        )
        assert_that(response_3.status_code, is_(201))
        assert_that(response_3.json["success"], is_("Docuement created successfully"))

        expense_payload_4 = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 60, "description": "Test Expense Entry Desription"},
                {"amount": 30, "description": "Test Expense Entry Desription"},
            ],
        }

        response_4 = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload_4)
        )
        assert_that(response_4.status_code, is_(201))
        assert_that(response_4.json["success"], is_("Docuement created successfully"))
        current_day_expense_id = response_4.json["_id"]
        current_day_expense = Expense.objects(id=current_day_expense_id).first()
        earlier_expense_remaining = current_day_expense.remaining_amount_till_now

        """
        Now, we will be deleting one of this expense entries
        for ex. 150 is removed
        (current_day - 2) => 150, 50 ---- 200 ---- 700

        Hence, current and upper expenses will be

        (current_day - 2) =>
            50 ---- 50 ---- 850

        (current_day - 1) =>
            50, 60 ---- 110 ---- 590 + 150 = 740

        (current_day) =>
            30, 60 ---- 90 ---- 500 + 150 => 650
        """

        expense_id = response_2.json["_id"]
        expense = Expense.objects(id=expense_id).first()
        ee_map = {doc.ee_id: doc.amount for doc in expense.expenses}
        ee_id = random.choice(list(ee_map.keys()))  # select random e
        deleted_response = self.expense_helper.delete_expense_entry_api(
            self.api_token, str(expense_id), ee_id
        )
        assert_that(deleted_response.status_code, is_(204))  # No content
        removed_amount = ee_map[ee_id]

        current_day_1_expense_id = response_3.json["_id"]
        current_day_expense_id = response_4.json["_id"]

        current_day_1_expense = Expense.objects(id=current_day_1_expense_id).first()
        current_day_expense = Expense.objects(id=current_day_expense_id).first()

        assert_that(
            current_day_1_expense.remaining_amount_till_now, is_(removed_amount + 590)
        )
        assert_that(
            current_day_expense.remaining_amount_till_now, is_(removed_amount + 500)
        )

        # finally check the bank's balance, which should be increased by removed_amount
        bank = current_day_expense.get_bank()
        assert_that(
            bank.current_balance,
            is_(removed_amount + earlier_expense_remaining),
        )

    def test_delete_last_expense_entry(self):
        bank = BankFactory.get_bank(self.user.id)
        bank.save()

        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 50, "description": "Test Expense Entry Desription"},
            ],
        }
        response = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        assert_that(response.status_code, is_(201))
        assert_that(response.json["success"], is_("Docuement created successfully"))
        bank.reload()  # reloading that bank object again.
        assert_that(bank.current_balance, is_(950))

        expense_id = response.json["_id"]
        ee_id = 1

        # The reason behind writing this test case is because of if we are
        # trying to delete the remaining only one expense entry, then it
        # is going to delete the whole expense as well.
        deleted_response = self.expense_helper.delete_expense_entry_api(
            self.api_token, str(expense_id), ee_id
        )
        assert_that(deleted_response.status_code, is_(204))  # No content
        expense = Expense.objects(id=expense_id).first()
        assert_that(expense, is_(None))  # we won't get that expense now

        bank.reload()  # reloading the bank again.
        assert_that(bank.current_balance, is_(1000))

        # Creting the same day expense again, so that we won't get the NotUnique error
        expense_payload = {
            "bank_id": str(bank.id),
            "created_at": provide_todays_date(),
            "expenses": [
                {"amount": 125, "description": "Test Expense Entry Desription"},
            ],
        }
        response = self.expense_helper.create_expense_api(
            self.api_token, params=json.dumps(expense_payload)
        )
        bank.reload()  # reloading the bank again.
        assert_that(bank.current_balance, is_(1000 - 125))
