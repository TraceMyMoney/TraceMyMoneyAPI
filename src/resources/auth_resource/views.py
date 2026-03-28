import jwt
from http import HTTPStatus
from datetime import datetime, timedelta
from webargs.flaskparser import use_kwargs
from werkzeug.security import check_password_hash
from flask_apispec import marshal_with

from src.extensions import config
from src.common.base_resource import BaseResource
from src.models.model_db_methods.user_db_methods import UserDBMethods
from src.resources.auth_resource.schema import (
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    UserRegisterRequestSchema,
    UserRegisterResponseSchema,
)


class UserLoginResource(BaseResource):

    @use_kwargs(UserLoginRequestSchema, location="json")
    @marshal_with(UserLoginResponseSchema, HTTPStatus.OK)
    def post(self, **kwargs):
        if user := UserDBMethods.get_record_with_(username=kwargs["username"]):
            if check_password_hash(user.password, kwargs["password"]):
                token = jwt.encode(
                    {
                        "user_id": str(user.id),
                        "user_name": user.username,
                        "exp": datetime.utcnow() + timedelta(minutes=config.get("JWT_EXPIRATION_MINUTES")),
                    },
                    config.get("JWT_SECRET_KEY"),
                )
                return {"token": token}

        raise ValueError("Invalid username or password")


class UserRegisterResource(BaseResource):

    @use_kwargs(UserRegisterRequestSchema, location="json")
    @marshal_with(UserRegisterResponseSchema, HTTPStatus.CREATED)
    def post(self, **kwargs):
        if UserDBMethods.get_user_with_email_or_username(
            username=kwargs["username"], email=kwargs["email"]
        ):
            raise ValueError("User already exists")

        UserDBMethods.create_record(kwargs)
        return {"message": "User created successfully"}, HTTPStatus.CREATED
