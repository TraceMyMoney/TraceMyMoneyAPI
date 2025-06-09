# libraries imports
from flask_cors import CORS
from flask import Blueprint, jsonify, current_app, request
from werkzeug.exceptions import BadRequest
from json import loads


from src.schemas.schemas import UserPreferenceSchema
from src.models.model_db_methods.user_preferences_db_methods import (
    UserPreferenceDBMethods,
)
from src.helpers.authentication import token_required


user_preferences_bp = Blueprint("user_preferences", __name__)
CORS(user_preferences_bp, resources={r"/*": {"origins": "*"}})


@user_preferences_bp.get("/")
@token_required
def user_preferences(current_user):
    user_preferences = UserPreferenceDBMethods.get_record_with_(user_id=current_user.id)
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}" f"\nFile Name : {__name__}"
    )
    results = UserPreferenceSchema().dump(user_preferences)

    return (
        jsonify({"user_preferences": results}),
        200,
    )


@user_preferences_bp.patch("/update")
@token_required
def update_user_preferences(current_user):
    data = loads(request.data.decode("utf-8"))
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}" f"\nFile Name : {__name__}"
    )
    if user_preference := UserPreferenceDBMethods.get_record_with_(
        user_id=current_user.id
    ):
        update_dict = {}
        if (is_dark_mode := data.get("is_dark_mode")) is not None:
            update_dict["set__is_dark_mode"] = is_dark_mode

        if page_size := data.get("page_size"):
            update_dict["set__page_size"] = page_size

        if banks_display_order := data.get("banks_display_order"):
            update_dict["set__banks_display_order"] = banks_display_order

        if (privacy_mode_enabled := data.get("privacy_mode_enabled")) is not None:
            update_dict["set__privacy_mode_enabled"] = privacy_mode_enabled

        if user_preference.update(**update_dict):
            return (
                jsonify({"message": "Document updated successfully."}),
                200,
            )
        raise BadRequest("Preferences update failed")
