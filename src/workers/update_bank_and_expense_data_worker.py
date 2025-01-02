# libraries imports
from celery import shared_task
from datetime import datetime
from bson import ObjectId
from flask import current_app

# relative imports
from src.models.expense import Expense
from src.models.bank import Bank
from src.models.user import User
from src.helpers import helper


@shared_task(ignore_result=False)
def update_bank_and_expense_data(
    bank_id="",
    expense_id="",
    is_newly_created=True,
    total_entry_entered=None,
    user_id=None,
):
    # Get the current user
    current_user = User.objects(id=ObjectId(user_id)).first()
    helper.configure_logging(current_app)
    current_app.logger.info(
        f"\nCurrent user id : {str(current_user.id)}" f"\nFile name: {__name__}"
    )
    if current_user and bank_id and expense_id:
        bank = Bank.objects(id=bank_id, user_id=current_user.id).first()
        expense = Expense.objects(
            id=expense_id, user_id=current_user.id, bank=bank.id
        ).first()
        above_expenses = Expense.objects(
            created_at__gt=expense.created_at, bank=bank.id, user_id=current_user.id
        ).order_by("-created_at")

        if bank and expense:
            expense_data_to_update = {}
            bank_data_to_update = {}
            update_above_expenses = {}

            if is_newly_created:
                previous_expense = (
                    Expense.objects(
                        created_at__lt=expense.created_at,
                        bank=bank.id,
                        user_id=current_user.id,
                    )
                    .order_by("-created_at")
                    .first()
                )
                if previous_expense:
                    amount_from_which_deducted_from = (
                        previous_expense.remaining_amount_till_now
                    )
                else:
                    amount_from_which_deducted_from = bank.current_balance

                total_disbursed_till_now = (
                    bank.total_disbursed_till_now + expense.expense_total
                )

                expense_data_to_update.update(
                    set__remaining_amount_till_now=amount_from_which_deducted_from
                    - expense.expense_total,
                    set__updated_at=datetime(
                        *helper.provide_todays_date(str_format=False)
                    ),
                )
                bank_data_to_update.update(
                    set__total_disbursed_till_now=total_disbursed_till_now,
                    set__current_balance=bank.current_balance - expense.expense_total,
                    set__updated_at=datetime(
                        *helper.provide_todays_date(str_format=False)
                    ),
                )
                update_above_expenses = {
                    "inc__remaining_amount_till_now": -(expense.expense_total)
                }
            else:
                if total_entry_entered is not None:
                    expense_data_to_update.update(
                        set__expense_total=(
                            expense.expense_total + total_entry_entered
                        ),
                        set__remaining_amount_till_now=(
                            expense.remaining_amount_till_now - total_entry_entered
                        ),
                    )
                    bank_data_to_update.update(
                        set__total_disbursed_till_now=(
                            bank.total_disbursed_till_now + total_entry_entered
                        ),
                        set__current_balance=bank.current_balance - total_entry_entered,
                    )
                    update_above_expenses = {
                        "inc__remaining_amount_till_now": -(total_entry_entered)
                    }

            if above_expenses:
                above_expenses.update(
                    **update_above_expenses,
                    multi=True,
                )
            expense.update(**expense_data_to_update)
            bank.update(**bank_data_to_update)
            bank.reload()
