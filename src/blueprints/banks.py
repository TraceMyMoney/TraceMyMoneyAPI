# libraries imports
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from json import loads
from datetime import datetime
from mongoengine import ValidationError
from bson import ObjectId

# relative imports
from src.models.bank import Bank
from src.constants import DATE_TIME_FORMAT
from src.schemas.schemas import BankSchema
from src.helpers.authentication import token_required
from src.models.expense import Expense

bank_bp = Blueprint("banks", __name__)
CORS(bank_bp, resources={r"/*": {"origins": "*"}})


@bank_bp.get("/")
@token_required
def banks(current_user):
    result = BankSchema().dump(
        Bank.get_banks(current_user, **dict(request.args)), many=True
    )
    return jsonify({"banks": result}), 200


@bank_bp.post("/create")
@token_required
def create_bank(current_user):
    data = loads(request.data.decode("utf-8"))
    if data.get("created_at"):
        data["created_at"] = datetime.strptime(data.get("created_at"), DATE_TIME_FORMAT)

    try:
        if Bank(user_id=current_user.id, **data).save():
            return jsonify({"success": "Bank object saved successfully"})
    except ValidationError as err:
        return jsonify({"error": [obj.message for _, obj in err.errors.items()]}), 400
    except Exception as err:
        return jsonify({"error": "Error while saving the bank object"})


@bank_bp.delete("/delete")
@token_required
def delete_bank(current_user):
    data = loads(request.data.decode("utf-8"))
    if bank_id := data.get("bank_id"):
        if bank := Bank.objects(id=bank_id, user_id=current_user.id).first():
            if expenses := Expense.objects(
                bank=ObjectId(bank_id), user_id=current_user.id
            ):
                if expenses.count() > 0:
                    expenses.delete()
            bank.delete()
            return jsonify({"success": "Bank deleted successfully"})
        else:
            return jsonify({"error": "Bank not found with provided ID"}), 400
    else:
        return jsonify({"error": "Please provide the bank id to delete"}), 400
