from marshmallow import fields, Schema, validate
from src.constants import DATE_TIME_FORMAT


class ListEETagRequestSchema(Schema):
    name = fields.String()
    user_id = fields.String()


class EETagResponseSchema(Schema):
    name = fields.String()
    user_id = fields.String()


class ListEETagResponseSchema(Schema):
    tags = fields.List(fields.Nested(EETagResponseSchema))


class CreateEETagRequestSchema(Schema):
    name = fields.String(required=True, validate=[validate.Length(min=1, max=50)])
    user_id = fields.String(required=True)


class CreateEETagResponseSchema(Schema):
    message = fields.String()
