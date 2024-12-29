# libraries imports
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from json import loads
from datetime import datetime
from mongoengine import ValidationError

# relative imports
from src.models.bank import Bank
from src.constants import DATE_TIME_FORMAT
from src.schemas.schemas import BankSchema
from src.helpers.authentication import token_required

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
