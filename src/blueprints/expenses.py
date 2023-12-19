from flask import Blueprint, jsonify, request
from models.expense import Expense
from models.bank import Bank
from models.expense_entry import ExpenseEntry
from schemas.schemas import ExpenseSchema
from json import loads
from datetime import datetime
from constants import DATE_TIME_FORMAT

expense_bp = Blueprint('expenses', __name__)

@expense_bp.get('/')
def expenses():
    expenses = Expense.get_expenses(**dict(request.args)).order_by('created_at')
    results = ExpenseSchema().dump(expenses, many=True)
    return jsonify({
        'expenses': results
    }), 200

@expense_bp.post('/create')
def create_expense():
    data = loads(request.data.decode('utf-8'))
    if data.get('bank_id'):
        bank = Bank.objects(id=data.get('bank_id')).first()
        if bank:
            expense = __create_expense_object(data, bank)
            try:
                if expense.save():
                    return jsonify({
                        'success': 'Docuement created successfully'
                    }), 201
            except Exception as err:
                return jsonify({
                    'error': err.message
                }), 500
        else:
            return jsonify({
                'error': 'bank not found for the corresponding id'
            }), 400
    else:
        return jsonify({
            'error': 'please provide bank_id'
        }), 400

@expense_bp.post('/create-bulk')
def create_bulk_expenses():
    records = loads(request.data.decode('utf-8'))
    valid_objects = []
    for data in records:
        if data.get('bank_id'):
            bank = Bank.objects(id=data.get('bank_id')).first()
            if bank:
                expense = __create_expense_object(data, bank)
                valid_objects.append(expense)
            else:
                return jsonify({
                    'error': 'Bank not found'
                }), 201
    try:
        if Expense.objects.insert(valid_objects):
            return jsonify({
                'success': 'Docuements inserted successfully'
            }), 201
    except Exception as err:
        return jsonify({
            'error': err.message
        }), 500

@expense_bp.delete('/delete')
def delete_expense():
    params = dict(request.args)
    if params.get('id'):
        try:
            expense = Expense.objects(id=params.get('id')).first()
            if expense:
                expense.delete()
                return jsonify({
                    'deleted': 'Document deleted successfully'
                }), 204
            else:
                return jsonify({
                    'error': 'Document not found'
                }), 404
        except AttributeError as err:
            return jsonify({
                'error': err.args
            }), 500
        except Exception as e:
            return jsonify({
                'error': 'Error while deleting the document'
            }), 500
    else:
        return jsonify({
            'error': 'Please provide the Expense ID'
        }), 400

def __create_expense_object(data, bank):
    # TODO: apply DATE_TIME_FORMAT here
    created_at = datetime.strptime(data.get('created_at'), DATE_TIME_FORMAT)
    updated_at = datetime.strptime(data.get('updated_at'), DATE_TIME_FORMAT)
    ee_list = []
    if data.get('expenses'):
        for entry in data.get('expenses'):
            expense_entry = ExpenseEntry( amount=entry.get('amount'),
                                            description=entry.get('description'),
                                            created_at=created_at,
                                            updated_at=updated_at )

            if entry.get('type'):
                expense_entry.expense_entry_type = entry.get('type')
            ee_list.append(expense_entry)

    return Expense(bank=bank, created_at=created_at, updated_at=created_at, expenses=ee_list)
