from marshmallow import fields, Schema, validate, validate
from src.constants import DATE_TIME_FORMAT


class DaterangeSchema(Schema):
    start_date = fields.DateTime(format=DATE_TIME_FORMAT)
    end_date = fields.DateTime(format=DATE_TIME_FORMAT)


# GET
class ExpensesListRequestSchema(Schema):
    page_number = fields.Integer(required=True, validate=[validate.Range(min=1)])
    per_page = fields.Integer(required=True, validate=[validate.Range(min=1)])
    user_id = fields.String(required=True, validate=[validate.Length(equal=24)])
    bank_id = fields.String(required=True, validate=[validate.Length(equal=24)])
    advanced_search = fields.Boolean(default=False)
    search_by_tags = fields.List()
    search_by_keyword = fields.String()
    search_by_bank_ids = fields.List()
    search_by_daterange = fields.Nested(DaterangeSchema)
    operator = fields.String(validate=[validate.Length(min=1, max=5)])
