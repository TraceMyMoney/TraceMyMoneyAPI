import jwt
from functools import wraps
from flask import request, g

from src.models.user import User
from src.extensions import config
from src.utils.resource_exceptions import AuthorizationException


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "x-access-token" in request.headers:
            token = request.headers["x-access-token"]
        if not token:
            raise AuthorizationException("Token is missing")
        try:
            data = jwt.decode(token, config["JWT_SECRET_KEY"], algorithms=["HS256"])
            if not (current_user := User.objects(id=data["user_id"]).first()):
                raise AuthorizationException("User not found")
            g.current_user = current_user
        except:
            raise AuthorizationException("Token is invalid")
        return f(*args, **kwargs)

    return decorated
