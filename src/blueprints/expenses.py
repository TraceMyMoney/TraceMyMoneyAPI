# libraries imports
from flask import Blueprint, jsonify, request
from json import loads
from flask_cors import CORS
from datetime import datetime
from mongoengine import NotUniqueError

# relative imports
from src.constants import DATE_TIME_FORMAT
from src.models.expense import Expense
from src.models.bank import Bank
from src.models.expense_entry import ExpenseEntry
from src.schemas.schemas import ExpenseSchema
from src.helpers import helper

expense_bp = Blueprint('expenses', __name__)
CORS(expense_bp, resources={r"/*": {"origins": "*"}})

@expense_bp.get('/')
def expenses():
    expenses = Expense.get_expenses(**dict(request.args)).order_by('-created_at')
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

            except NotUniqueError as err:
                return jsonify({
                    'error': 'You cannot replicate the expense for the same day.'
                }), 500

            except Exception as err:
                return jsonify({
                    'error': err.message if hasattr(err, 'message') else 'Default Error'
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
            'error': err.message if hasattr(err, 'message') else 'Default Error'
        }), 500

# All updates regarding expenses
@expense_bp.patch('/add-entry')
def add_expense_entry():
    params = request.args
    if params.get('id'):
        expense = Expense.objects(id=params['id']).first()
        if expense:
            entry_records = [ExpenseEntry(**entry_record) for entry_record in loads(request.data.decode('utf-8'))]
            total_entry_entered = sum((entry_record.amount for entry_record in entry_records))
            expense.update(push_all__expenses=entry_records)
            expense.total_entry_entered = total_entry_entered # dynamic attribute
            expense.save()
        else:
            return jsonify({
                'error': 'Expense not found for provided ID'
            }), 400
        return jsonify({
            'success': 'Added expense successfully'
        }), 201
    else:
        return jsonify({
            'error': 'Please enter the expense ID to udpate'
        }), 400

@expense_bp.delete('/delete')
def delete_expense():
    params = dict(request.args)
    if params.get('id'):
        try:
            # TODO : validate the expense as top of stack before deletion
            # or let uesr delete any expense, but all other expenses above it, needs to be updated !
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
        except Exception:
            return jsonify({
                'error': 'Error while deleting the document'
            }), 500
    else:
        return jsonify({
            'error': 'Please provide the Expense ID'
        }), 400

def __create_expense_object(data, bank):
    created_at = None
    if data.get('created_at'):
        created_at = datetime.strptime(data.get('created_at'), DATE_TIME_FORMAT)

    ee_list = []
    if data.get('expenses'):
        for entry in data.get('expenses'):
            expense_entry = ExpenseEntry(amount=entry.get('amount'),
                                         description=entry.get('description'),
                                         created_at=created_at)

            if entry.get('type'):
                expense_entry.expense_entry_type = entry.get('type')
            ee_list.append(expense_entry)

    return Expense(bank=bank, created_at=created_at, expenses=ee_list)
