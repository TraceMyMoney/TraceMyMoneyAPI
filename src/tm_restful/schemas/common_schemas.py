from marshmallow import Schema, fields


class SuccessSchema(Schema):
    success = fields.String()
