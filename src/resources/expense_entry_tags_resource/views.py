from flask import g
from http import HTTPStatus
from webargs.flaskparser import use_kwargs
from flask_apispec import marshal_with

from src.common.base_resource import BaseResource
from src.resources.expense_entry_tags_resource.schemas import (
    ListEETagRequestSchema,
    ListEETagResponseSchema,
    CreateEETagRequestSchema,
    CreateEETagResponseSchema,
)
from src.resources.expense_entry_tags_resource.model.expense_entry_tag_db_methods import (
    ExpenseEntryTagDBMethods,
)
from src.helpers.authentication import token_required
from src.constants import SUCCESS


class ExpenseEntryTagResource(BaseResource):

    @token_required
    @use_kwargs(ListEETagRequestSchema, location="querystring")
    @marshal_with(ListEETagResponseSchema, HTTPStatus.OK)
    def get(self, **kwargs):
        tags = ExpenseEntryTagDBMethods.get_tags(g.current_user, **kwargs)
        return {"tags": tags}

    @token_required
    @use_kwargs(CreateEETagRequestSchema, location="json")
    @marshal_with(CreateEETagResponseSchema, HTTPStatus.OK)
    def post(self, **kwargs):
        tag_name, user_id = kwargs["name"], kwargs["user_id"]
        if _ := ExpenseEntryTagDBMethods.get_record_with_(**{"name": tag_name, "user_id": user_id}):
            raise ValueError("Tag already exists")

        ExpenseEntryTagDBMethods.create_record(kwargs)
        return {"message": SUCCESS}
