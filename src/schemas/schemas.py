# libraries imports
from marshmallow import Schema, fields

# relative imports
from src.constants import DATE_TIME_FORMAT


class ExpenseEntryTagSchema(Schema):
    name = fields.String()
    user_id = fields.String()


class ExpenseEntrySchema(Schema):
    amount = fields.Float()
    description = fields.String()
    expense_entry_type = fields.String()
    ee_id = fields.Integer()
    entry_tags = fields.List(fields.String())
    created_at = fields.Date(DATE_TIME_FORMAT)
    updated_at = fields.Date(DATE_TIME_FORMAT)


class BankSchema(Schema):
    id = fields.String()
    name = fields.String()
    initial_balance = fields.Float()
    current_balance = fields.Float()
    total_disbursed_till_now = fields.Float()
    user_id = fields.String()
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


class UserPreferenceSchema(Schema):
    user_id = fields.String()
    is_dark_mode = fields.Boolean()
    page_size = fields.Integer()
    privacy_mode_enabled = fields.Boolean()
