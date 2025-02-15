# lib imports
from flask_apispec import use_kwargs, marshal_with
from flask import g
from http import HTTPStatus

# local import
from src_restful.base import BaseResource
from src_restful.schemas.common_schemas import SuccessSchema
from src_restful.resources.expenses.schemas import (
    ExpenseGetRequestSchema,
)
from src_restful.resources.expenses.model_db_methods.expense_db_methods import (
    ExpenseDBMethods,
)
from src.helpers.authentication import token_required


class ExpenseResource(BaseResource):

    @use_kwargs(ExpenseGetRequestSchema, location="query")
    @token_required
    def get(self, **kwargs):
        entry_tags = ExpenseDBMethods().get_expenses(
            current_user=g.current_user, **kwargs
        )
        return dict(entry_tags=entry_tags)

    # @use_kwargs(ExpenseEntryTagPostRequestSchema)
    # @marshal_with(ExpenseEntryTagPostResponseSchema, HTTPStatus.CREATED)
    # @token_required
    # def post(self, **kwargs):
    #     entry_tag = ExpenseDBMethods().create_tags(
    #         current_user=g.current_user, **kwargs
    #     )
    #     return dict(id=str(entry_tag))

    # @use_kwargs(ExpenseEntryTagDeleteRequestSchema)
    # @marshal_with(SuccessSchema, HTTPStatus.NO_CONTENT)
    # @token_required
    # def delete(self, **kwargs):
    #     entry_tag = ExpenseDBMethods().delete_tag(current_user=g.current_user, **kwargs)
    #     return dict(success="Tag deleted successfully")
