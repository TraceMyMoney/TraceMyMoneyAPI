from marshmallow import fields, Schema, validate, validate
from src.constants import DATE_TIME_FORMAT


# GET
class BanksListRequestSchema(Schema):
    id = fields.String(validate=[validate.Length(equal=24)])
    name = fields.String(validate=[validate.Length(min=1, max=15)])


class BanksNestedResponseSchema(Schema):
    id = fields.String()
    name = fields.String()
    initial_balance = fields.Float()
    current_balance = fields.Float()
    total_disbursed_till_now = fields.Float()
    user_id = fields.String()
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)


class BanksListResponseSchema(Schema):
    banks = fields.List(fields.Nested(BanksNestedResponseSchema), metadata=dict(many=True))


# POST
class BanksCreateRequestSchema(Schema):
    name = fields.String(required=True, validate=[validate.Length(max=15)])
    initial_balance = fields.Float(required=True, validate=validate.Range(min=0.0))


class BanksCreateResponseSchema(Schema):
    message = fields.String()


class BankDeleteResponseSchema(Schema):
    pass
