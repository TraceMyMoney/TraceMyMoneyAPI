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
    search_by_tags = fields.List(fields.String(validate=[validate.Length(equal=24)]))
    search_by_bank_ids = fields.List(fields.String(validate=[validate.Length(equal=24)]))
    search_by_keyword = fields.String()
    search_by_daterange = fields.Nested(DaterangeSchema)
    operator = fields.String(validate=[validate.Length(min=1, max=5)])


class ExpenseEntrySchema(Schema):
    amount = fields.Float()
    description = fields.String()
    expense_entry_type = fields.String()
    ee_id = fields.Integer()
    entry_tags = fields.List(fields.String())
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)


class ExpenseSchema(Schema):
    id = fields.String()
    day = fields.String()
    expenses = fields.List(fields.Nested(ExpenseEntrySchema))
    bank_name = fields.String()
    remaining_amount_till_now = fields.Float()
    expense_total = fields.Float()
    topup_expense_total = fields.Float()
    user_id = fields.String()
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)


class ExpensesListResponseSchema(Schema):
    total_expenses = fields.Integer()
    non_topup_total = fields.Float()
    topup_total = fields.Float()
    expenses = fields.List(fields.Nested(ExpenseSchema), many=True)


# POST
class CreateExpenseEntryRequestSchema(Schema):
    amount = fields.Float(required=True)
    description = fields.String(required=True)
    selected_tags = fields.List(fields.String())


class CreateExpensesRequestSchema(Schema):
    bank_id = fields.String(required=True)
    expenses = fields.List(
        fields.Nested(CreateExpenseEntryRequestSchema), validate=[validate.Length(min=1)]
    )
    created_at = fields.DateTime(format=DATE_TIME_FORMAT)


class CommonExpenseResponseSchema(Schema):
    message = fields.String()
