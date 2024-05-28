# libraries imports
from flask import Blueprint, jsonify, request
from json import loads
from datetime import datetime
from mongoengine import ValidationError

# relative imports
from src.models.bank import Bank
from src.constants import DATE_TIME_FORMAT
from src.schemas.schemas import BankSchema

bank_bp = Blueprint('banks', __name__)

@bank_bp.get('/')
def banks():
    result = BankSchema().dump(Bank.get_banks(**dict(request.args)), many=True)
    return jsonify({
        'banks': result
    }), 200

@bank_bp.post('/create')
def create_bank():
    data = loads(request.data.decode('utf-8'))
    if data.get('created_at'):
        data['created_at'] = datetime.strptime(data.get('created_at'), DATE_TIME_FORMAT)

    try:
        if Bank(**data).save():
            return jsonify({
                'success': 'Bank object saved successfully'
            })
    except ValidationError as err:
        return jsonify({
            'error': [obj.message for _, obj in err.errors.items()]
        })
    except Exception as err:
        return jsonify({
            'error': 'Error while saving the bank object'
        })
