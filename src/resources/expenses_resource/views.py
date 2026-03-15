from flask import g
from http import HTTPStatus
from webargs.flaskparser import use_kwargs
from flask_apispec import marshal_with

from src.extensions import config
from src.resources.banks_resource.model.bank_db_methods import BankDBMethods
from src.common.base_resource import BaseResource
from src.helpers.authentication import token_required
from src.resources.expenses_resource.schemas import (
    ExpensesListRequestSchema,
    ExpensesListResponseSchema,
    CreateExpensesRequestSchema,
    CommonExpenseResponseSchema,
)
from src.resources.expenses_resource.model.expense_db_methods import ExpenseDBMethods
from src.constants import SUCCESS


class ExpensesResource(BaseResource):

    @token_required
    @use_kwargs(ExpensesListRequestSchema, location="querystring")
    @marshal_with(ExpensesListResponseSchema, HTTPStatus.OK)
    def get(self, **kwargs):
        expenses, total_expenses, non_topup_total, topup_total = ExpenseDBMethods.get_expenses(
            g.current_user, **kwargs
        )
        return {
            "expenses": expenses,
            "total_expenses": total_expenses,
            "non_topup_total": non_topup_total,
            "topup_total": topup_total,
        }

    @token_required
    @use_kwargs(CreateExpensesRequestSchema, location="json")
    @marshal_with(CommonExpenseResponseSchema, HTTPStatus.CREATED)
    def post(self, **kwargs):
        if not (bank := BankDBMethods.get_record_with_id(kwargs["bank_id"])):
            raise ValueError("Bank doesn't exists")

        ExpenseDBMethods.create_record(kwargs, bank, current_user=g.current_user)
        return {"message": SUCCESS}, HTTPStatus.CREATED
