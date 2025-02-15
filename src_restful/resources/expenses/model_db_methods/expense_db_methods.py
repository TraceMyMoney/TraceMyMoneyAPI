# libraries imports
from datetime import datetime
from bson import ObjectId
from functools import reduce

# relative imports
from src_restful.constants import DATE_TIME_FORMAT
from src_restful.resources.expenses.model_db_methods.model.expense import Expense


class ExpenseDBMethods:

    @classmethod
    def get_total_of_expenses(cls, expense):
        return expense.get_total_of_expenses()

    @classmethod
    def get_bank(cls, expense):
        return expense.get_bank()

    @classmethod
    def get_expenses(cls, current_user, **kwargs):
        return Expense.get_expenses(current_user, **kwargs)
