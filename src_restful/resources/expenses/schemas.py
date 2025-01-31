from marshmallow import Schema, fields, validates_schema


# GET ------------------------------------------------


class DateRangeSchema(Schema):
    start_date = fields.DateTime()
    end_date = fields.DateTime()


class ExpenseGetRequestSchema(Schema):
    search_by_tags = fields.List(fields.String())
    search_by_keyword = fields.String()
    search_by_bank_ids = fields.List(fields.String())
    search_by_daterange = fields.Nested(DateRangeSchema)
    page_number = fields.Integer()
    per_page = fields.Integer()
    advanced_search = fields.Boolean()

    @validates_schema
    def validate(self, data, **kwargs):
        pass


class ExpenseGetResponseSchema(Schema):
    expenses = fields.Nested()
    total_number_of_expenses = fields.Nested()
    non_topup_total = fields.Integer()
    topup_total = fields.Integer()


# ------------------------------------------------
