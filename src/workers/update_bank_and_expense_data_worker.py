from celery import shared_task
from datetime import datetime

from models.expense import Expense
from models.bank import Bank
from helpers import helper

@shared_task(ignore_result=False)
def update_bank_and_expense_data(bank_id='', expense_id='', is_newly_created=True):
    if bank_id and expense_id:
        bank = Bank.objects(id=bank_id).first()
        expense = Expense.objects(id=expense_id).first()

        if bank and expense:
            expense_data_to_update = {}
            bank_data_to_update = {}

            if is_newly_created:
                remaining_amount_till_now = bank.current_balance - expense.expense_total
                total_disbursed_till_now = bank.total_disbursed_till_now + expense.expense_total

                expense_data_to_update.update(
                    set__remaining_amount_till_now=remaining_amount_till_now,
                    set__updated_at=datetime(*helper.provide_todays_date(str_format=False)),
                )
                bank_data_to_update.update(
                    set__total_disbursed_till_now=total_disbursed_till_now,
                    set__current_balance=remaining_amount_till_now,
                    set__updated_at=datetime(*helper.provide_todays_date(str_format=False)),
                    push__expenses=expense
                )
            else:
                expense_bank_current_balance = bank.current_balance - expense.total_entry_entered

                expense_data_to_update.update(
                    set__expense_total=(expense.expense_total + expense.total_entry_entered),
                    set__remaining_amount_till_now=expense_bank_current_balance
                )
                bank_data_to_update.update(
                    set__total_disbursed_till_now=(bank.total_disbursed_till_now + expense.total_entry_entered),
                    set__current_balance=expense_bank_current_balance,
                )

            expense.update(**expense_data_to_update)
            bank.update(**bank_data_to_update)
            bank.reload()
