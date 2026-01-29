from marshmallow import fields, Schema, validate, validate


class UserLoginRequestSchema(Schema):
    username = fields.String(required=True, validate=[validate.Length(min=1, max=50)])
    password = fields.String(required=True, validate=[validate.Length(min=1, max=15)])


class UserLoginResponseSchema(Schema):
    token = fields.String(required=True)


class UserRegisterRequestSchema(Schema):
    username = fields.String(required=True, validate=[validate.Length(min=1, max=50)])
    email = fields.String(required=True, validate=[validate.Length(min=1, max=50)])
    password = fields.String(required=True, validate=[validate.Length(min=1, max=15)])


class UserRegisterResponseSchema(Schema):
    message = fields.String(required=True)
