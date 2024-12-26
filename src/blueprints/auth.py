import jwt
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from json import loads
from mongoengine import ValidationError
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta

from src.models.user import User
from src.extensions import config


auth_bp = Blueprint("auth", __name__)
CORS(auth_bp, resources={r"/*": {"origins": "*"}})


@auth_bp.post("/login")
def login():
    login_details = loads(request.data.decode("utf-8"))
    if not (user_name := login_details.get("username")) or not (
        user_password := login_details.get("password")
    ):
        return jsonify({"error": "Could not verify"}), 401

    if user := User.objects(username=user_name).first():
        if check_password_hash(user.password, user_password):
            token = jwt.encode(
                {
                    "user_id": str(user.id),
                    "exp": datetime.utcnow() + timedelta(minutes=30),
                },
                config.get("JWT_SECRET_KEY"),
            )
            return jsonify({"token": token, "status_code": 201})
    else:
        jsonify({"error": "Could not find the user"}), 401


@auth_bp.post("/register")
def register():
    user_details = loads(request.data.decode("utf-8"))
    if User.objects(
        username=user_details.get("username"), email=user_details.get("email")
    ).first():
        return jsonify(
            {"errors": "User already exists either with given username or email"}
        )
    try:
        user = User(**user_details)
        user.validate()
        if created_user := user.save():
            return jsonify(
                {
                    "success": "User created successfully",
                    "user_id": str(created_user.id),
                }
            )
    except ValidationError as e:
        return jsonify({"errors": [{k: v.message} for k, v in e.errors.items()]})
