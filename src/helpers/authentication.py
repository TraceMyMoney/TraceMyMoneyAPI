import jwt
from functools import wraps
from flask import jsonify, request

from src.models.user import User
from src.extensions import config


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "x-access-token" in request.headers:
            token = request.headers["x-access-token"]
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            data = jwt.decode(token, config["JWT_SECRET_KEY"], algorithms=["HS256"])
            current_user = User.objects(id=data["user_id"]).first()
            if not current_user:
                return jsonify({"error": "User not found"}), 401
        except:
            return jsonify({"message": "Token is invalid"}), 401
        return f(current_user, *args, **kwargs)

    return decorated
