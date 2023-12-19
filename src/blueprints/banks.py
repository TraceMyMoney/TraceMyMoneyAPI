from flask import Blueprint, jsonify, request
from models.bank import Bank
from json import loads
from constants import DATE_TIME_FORMAT
from datetime import datetime
from schemas.schemas import BankSchema
from mongoengine import ValidationError

bank_bp = Blueprint('banks', __name__)

@bank_bp.get('/')
def banks():
    result = BankSchema().dump(Bank.objects(), many=True)
    return jsonify({
        'banks': result
    }), 200

@bank_bp.post('/create')
def create_bank():
    data = loads(request.data.decode('utf-8'))
    data['created_at'] = datetime.strptime(data.get('created_at'), DATE_TIME_FORMAT)
    data['updated_at'] = datetime.strptime(data.get('updated_at'), DATE_TIME_FORMAT)
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
