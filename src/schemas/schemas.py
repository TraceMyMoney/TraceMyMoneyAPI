from marshmallow import Schema, fields

from constants import DATE_TIME_FORMAT

class ExpenseEntrySchema(Schema):
    amount = fields.Float()
    description = fields.String()
    expense_entry_type = fields.String()


class BankSchema(Schema):
    id = fields.String()
    name = fields.String()
    initial_balance = fields.Float()
    current_balance = fields.Float()
    remaining_balance = fields.Float()
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)


class ExpenseSchema(Schema):
    id = fields.String()
    day = fields.String()
    expenses = fields.List(fields.Nested(ExpenseEntrySchema))
    bank_name = fields.String()
    expense_total = fields.Float()
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)
