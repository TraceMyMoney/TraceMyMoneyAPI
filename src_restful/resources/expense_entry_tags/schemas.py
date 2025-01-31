from marshmallow import Schema, fields, validates_schema
from src_restful.resources.expense_entry_tags.model_db_methods.model.ExpenseEntryTag import (
    ExpenseEntryTag,
)
from src_restful.utils.exception import (
    EntryTagExistsError,
    ValueErrorWithoutNotification,
)


# GET
class ExpenseEntryTagSchema(Schema):
    id = fields.String()
    name = fields.String()


class ExpenseEntryTagRequestSchema(Schema):
    _id = fields.String()
    name = fields.String()
    user_id = fields.String()
    regex = fields.Boolean()


class ExpenseEntryTagResponseSchema(Schema):
    entry_tags = fields.List(
        fields.Nested(ExpenseEntryTagSchema), metadata=dict(many=True)
    )


# POST
class ExpenseEntryTagPostRequestSchema(Schema):
    name = fields.String()

    @validates_schema
    def validate(self, data, **kwargs):
        if not data.get("name"):
            raise ValueErrorWithoutNotification("Please provide the name")
        if ExpenseEntryTag.is_entry_exists(data.get("name")):
            raise EntryTagExistsError("Tag already exists")


class ExpenseEntryTagPostResponseSchema(Schema):
    id = fields.String()


# DELETE
class ExpenseEntryTagDeleteRequestSchema(Schema):
    _id = fields.String()

    @validates_schema
    def validate(self, data, **kwargs):
        if not data.get("_id"):
            raise ValueErrorWithoutNotification("Please provide the id")
