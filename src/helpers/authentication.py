import jwt
from functools import wraps
from flask import jsonify, request, g

from src.models.user import User
from src.extensions import config
from src.tm_restful.utils.exception import NoAuthorizationError


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "x-access-token" in request.headers:
            token = request.headers["x-access-token"]
        if not token:
            raise NoAuthorizationError(f"Missing Authorization Header")
        try:
            data = jwt.decode(token, config["JWT_SECRET_KEY"], algorithms=["HS256"])
            current_user = User.objects(id=data["user_id"]).first()
            if not current_user:
                raise NoAuthorizationError("Invalid credentials")
            g.current_user = current_user
        except:
            raise NoAuthorizationError("Signature verification failed")
        return f(*args, **kwargs)

    return decorated
