from http import HTTPStatus
from webargs.flaskparser import use_kwargs
from flask_apispec import marshal_with
from flask import g

from src.common.base_resource import BaseResource
from src.resources.banks_resource.schemas import (
    BanksListRequestSchema,
    BanksListResponseSchema,
    BanksCreateRequestSchema,
    BanksCreateResponseSchema,
    BankDeleteResponseSchema,
)
from src.resources.banks_resource.model.bank_methods import BankDBMethods
from src.helpers.authentication import token_required
from src.constants import SUCCESS


class BanksResource(BaseResource):

    @token_required
    @use_kwargs(BanksListRequestSchema, location="querystring")
    @marshal_with(BanksListResponseSchema, HTTPStatus.OK)
    def get(self, **kwargs):
        banks = BankDBMethods.get_banks(g.current_user, **kwargs)
        return {"banks": banks}

    @token_required
    @use_kwargs(BanksCreateRequestSchema, location="json")
    @marshal_with(BanksCreateResponseSchema, HTTPStatus.CREATED)
    def post(self, **kwargs):
        payload = {
            "current_balance": kwargs["initial_balance"],
            "total_disbursed_till_now": 0,
            "user_id": g.current_user.id,
            **kwargs,
        }
        BankDBMethods.create_record(payload)
        return {"message": SUCCESS}, HTTPStatus.CREATED


class BanksDetailsResource(BaseResource):

    @token_required
    @marshal_with(BankDeleteResponseSchema, HTTPStatus.NO_CONTENT)
    def delete(self, bank_id, **kwargs):
        if not (bank := BankDBMethods.get_record_with_id(bank_id)):
            raise ValueError("Bank doesn't exists")

        # TODO : delete the expenses from here as well once you build the ExpenseDBMethods
        # if expenses := Expense.objects(bank=ObjectId(bank_id), user_id=current_user.id):
        #     if expenses.count() > 0:
        #         expenses.delete()

        bank.delete()
        return {}, HTTPStatus.NO_CONTENT
