# libraries imports
from flask import Blueprint, jsonify, request, current_app
from json import loads
from flask_cors import CORS
from datetime import datetime
from mongoengine import NotUniqueError
from bson import ObjectId

# relative imports
from src.constants import DATE_TIME_FORMAT
from src.models.expense import Expense
from src.models.bank import Bank
from src.models.expense_entry import ExpenseEntry
from src.schemas.schemas import ExpenseSchema
from src.helpers.authentication import token_required

expense_bp = Blueprint("expenses", __name__)
CORS(expense_bp, resources={r"/*": {"origins": "*"}})


@expense_bp.get("/")
@token_required
def expenses(current_user):
    request_args = dict(request.args)
    payload = {}
    if request_data := request_args.pop("data", None):
        payload = loads(request_data)
    expenses, total_expenses, total_summation = Expense.get_expenses(
        current_user, **request_args, **payload
    )
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\nNumber of expenses retrieved : {len(expenses)}"
        f"\nFile Name : {__name__}"
    )
    results = ExpenseSchema().dump(expenses, many=True)
    results.extend(
        [
            {"total_expenses": total_expenses},
            {"total_summation": total_summation},
        ]
    )

    return (
        jsonify({"expenses": results}),
        200,
    )


@expense_bp.post("/create")
@token_required
def create_expense(current_user):
    data = loads(request.data.decode("utf-8"))
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\n/create [expense]: {data}"
        f"\nFile Name : {__name__}"
    )
    if data.get("bank_id"):
        bank = Bank.objects(id=data.get("bank_id")).first()
        if bank:
            if data.get("expenses"):
                expense = __create_expense_object(data, bank, current_user)
            else:
                return (
                    jsonify(
                        {
                            "error": "Atleast one expense entry should be present while creating the expense"
                        }
                    ),
                    400,
                )
            try:
                if expense.save():
                    return (
                        jsonify(
                            {
                                "success": "Docuement created successfully",
                                "_id": str(expense.id),
                            }
                        ),
                        201,
                    )

            except NotUniqueError as err:
                return (
                    jsonify(
                        {"error": "You cannot replicate the expense for the same day."}
                    ),
                    400,
                )

            except Exception as err:
                return (
                    jsonify(
                        {
                            "error": (
                                err.message
                                if hasattr(err, "message")
                                else "Default Error"
                            )
                        }
                    ),
                    500,
                )
        else:
            return jsonify({"error": "bank not found for the corresponding id"}), 400
    else:
        return jsonify({"error": "please provide bank_id"}), 400


@expense_bp.post("/create-bulk")
@token_required
def create_bulk_expenses(current_user):
    records = loads(request.data.decode("utf-8"))
    valid_objects = []
    for data in records:
        if data.get("bank_id"):
            bank = Bank.objects(id=data.get("bank_id")).first()
            if bank:
                expense = __create_expense_object(data, bank, current_user)
                valid_objects.append(expense)
            else:
                return jsonify({"error": "Bank not found"}), 201
    try:
        if Expense.objects.insert(valid_objects):
            return jsonify({"success": "Docuements inserted successfully"}), 201
    except Exception as err:
        return (
            jsonify(
                {"error": err.message if hasattr(err, "message") else "Default Error"}
            ),
            500,
        )


# All updates regarding expenses
@expense_bp.patch("/add-entry")
@token_required
def add_expense_entry(current_user):
    params = request.args
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\n/add-entry [expense]: {params}"
        f"\nFile Name: {__name__}"
    )
    if params.get("id"):
        expense = Expense.objects(id=params["id"], user_id=current_user.id).first()
        if expense:
            entry_records = [
                ExpenseEntry(**entry_record)
                for entry_record in loads(request.data.decode("utf-8"))
            ]
            total_entry_entered = sum(
                (entry_record.amount for entry_record in entry_records)
            )
            expense.update(push_all__expenses=entry_records)
            expense.total_entry_entered = total_entry_entered  # dynamic attribute
            expense.save()
        else:
            return jsonify({"error": "Expense not found for provided ID"}), 400
        return jsonify({"success": "Added expense successfully"}), 201
    else:
        return jsonify({"error": "Please enter the expense ID to udpate"}), 400


@expense_bp.patch("/update-entry")
@token_required
def update_expense_entry(current_user):
    data = loads(request.data.decode("utf-8"))
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\n/update-entry [expense]: {data}"
        f"\nFile Name: {__name__}"
    )
    if data.get("expense_id") and data.get("entry_id"):
        if selected_tags := data.get("selected_tags"):
            try:
                Expense.objects(
                    id=ObjectId(data["expense_id"]),
                    user_id=current_user.id,
                    expenses__ee_id=data["entry_id"],
                ).update(
                    set__expenses__S__entry_tags=selected_tags,
                    set__expenses__S__description=data.get("description")
                )
            except Exception as e:
                return jsonify({"error": e})
            else:
                return jsonify({"success": "Updated expense entry successfully"}), 201
        else:
            return jsonify({"error": "Please provide the tags"}), 400
    else:
        return jsonify({"error": "Please provide expense_id and entry_id"}), 400


@expense_bp.delete("/delete-entry")
@token_required
def delete_expense_entry(current_user):
    params = request.args
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\n/delete-entry [expense]: {params}"
        f"\nFile Name: {__name__}"
    )
    if params.get("id") and params.get("ee_id"):
        expense = Expense.objects(id=params["id"], user_id=current_user.id).first()
        if expense:
            # TODO: Make the schema validations here.
            entry_record = expense.expenses.filter(ee_id=params.get("ee_id"))[0]
            if entry_record:
                expense.update(pull__expenses=entry_record)
                expense.removed_entry_record_amount = (
                    entry_record.amount
                )  # dynamic attribute
                expense.save()
        else:
            return jsonify({"error": "Expense not found for provided ID"}), 400
        return jsonify({"success": "Deleted expense entry successfully"}), 204
    else:
        return (
            jsonify({"error": "Please enter the expense ID and entry ID to delete"}),
            400,
        )


@expense_bp.delete("/delete")
@token_required
def delete_expense(current_user):
    params = dict(request.args)
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}"
        f"\n/delete [expense]: {params}"
        f"\nFile Name: {__name__}"
    )
    if params.get("id"):
        try:
            # TODO : validate the expense as top of stack before deletion
            # or let uesr delete any expense, but all other expenses above it, needs to be updated !
            expense = Expense.objects(
                id=params.get("id"), user_id=current_user.id
            ).first()
            if expense:
                expense.delete()
                return jsonify({"deleted": "Document deleted successfully"}), 204
            else:
                return jsonify({"error": "Document not found"}), 404
        except AttributeError as err:
            return jsonify({"error": err.args}), 500
        except Exception:
            return jsonify({"error": "Error while deleting the document"}), 500
    else:
        return jsonify({"error": "Please provide the Expense ID"}), 400


def __create_expense_object(data, bank, current_user):
    created_at = None
    if data.get("created_at"):
        created_at = datetime.strptime(data.get("created_at"), DATE_TIME_FORMAT)

    ee_list = []
    if data.get("expenses"):
        for entry in data.get("expenses"):
            expense_entry = ExpenseEntry(
                amount=entry.get("amount"),
                description=entry.get("description"),
                created_at=created_at,
                entry_tags=entry.get("selected_tags", []),
            )

            if entry.get("type"):
                expense_entry.expense_entry_type = entry.get("type")
            ee_list.append(expense_entry)

    return Expense(
        bank=bank, created_at=created_at, expenses=ee_list, user_id=str(current_user.id)
    )
