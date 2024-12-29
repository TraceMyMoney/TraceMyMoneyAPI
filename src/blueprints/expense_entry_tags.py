# libraries imports
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from json import loads
from bson import ObjectId

from src.models.expense_entry_tag import ExpenseEntryTag
from src.helpers.authentication import token_required


entry_tags_bp = Blueprint("entry_tags", __name__)
CORS(entry_tags_bp, resources={r"/*": {"origins": "*"}})


@entry_tags_bp.get("/")
@token_required
def get_entry_tags(current_user):
    entry_tags = list(
        map(
            lambda tag_object: {"id": str(tag_object.id), "name": tag_object.name},
            ExpenseEntryTag.objects(user_id=current_user.id),
        )
    )
    return jsonify({"entry_tags": entry_tags}), 200


@entry_tags_bp.post("/create")
@token_required
def create_entry_tags(current_user):
    data = loads(request.data.decode("utf-8"))
    if tag_name := data.get("name"):
        if not ExpenseEntryTag.objects(name=tag_name, user_id=current_user.id).first():
            ee_tag = ExpenseEntryTag(user_id=current_user.id, **data)
            if ee_tag.save():
                return (
                    jsonify(
                        {"success": "tag created successfully", "id": str(ee_tag.id)}
                    ),
                    201,
                )
            return jsonify({"error": "Error while saving tag"}), 500
        return jsonify({"error": "Tag already exists"}), 400
    return jsonify({"error": "Please provide the name"}), 400


@entry_tags_bp.delete("/delete")
@token_required
def delete_entry_tags(current_user):
    data = loads(request.data.decode("utf-8"))
    if tag_id := data.get("id"):
        if ObjectId.is_valid(tag_id):
            if ee_tag := ExpenseEntryTag.objects(
                id=tag_id, user_id=current_user.id
            ).first():
                ee_tag.delete()
                return jsonify({"succes": "tag deleted successfully"})
            return jsonify({"error": "error while deleting the tag"}), 500
        return jsonify({"error": "please provide the correct object id"}), 400
    return jsonify({"error": "please provide the id"}), 400
