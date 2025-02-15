# lib imports
from flask_apispec import use_kwargs, marshal_with
from flask import g
from http import HTTPStatus

# local import
from src_restful.base import BaseResource
from src_restful.resources.expense_entry_tags.schemas import (
    ExpenseEntryTagRequestSchema,
    ExpenseEntryTagResponseSchema,
    ExpenseEntryTagPostRequestSchema,
    ExpenseEntryTagPostResponseSchema,
    ExpenseEntryTagDeleteRequestSchema,
)
from src_restful.schemas.common_schemas import SuccessSchema
from src_restful.resources.expense_entry_tags.model_db_methods.expense_entry_db_methods import (
    ExpenseEntryDBMethods,
)
from src.helpers.authentication import token_required


class ExpenseEntryTagResource(BaseResource):

    @use_kwargs(ExpenseEntryTagRequestSchema, location="query")
    @marshal_with(ExpenseEntryTagResponseSchema, HTTPStatus.OK)
    @token_required
    def get(self, **kwargs):
        entry_tags = ExpenseEntryDBMethods().get_tags(
            current_user=g.current_user, **kwargs
        )
        return dict(entry_tags=entry_tags)

    @use_kwargs(ExpenseEntryTagPostRequestSchema)
    @marshal_with(ExpenseEntryTagPostResponseSchema, HTTPStatus.CREATED)
    @token_required
    def post(self, **kwargs):
        entry_tag = ExpenseEntryDBMethods().create_tags(
            current_user=g.current_user, **kwargs
        )
        return dict(id=str(entry_tag))

    @use_kwargs(ExpenseEntryTagDeleteRequestSchema)
    @marshal_with(SuccessSchema, HTTPStatus.NO_CONTENT)
    @token_required
    def delete(self, **kwargs):
        entry_tag = ExpenseEntryDBMethods().delete_tag(
            current_user=g.current_user, **kwargs
        )
        return dict(success="Tag deleted successfully")
