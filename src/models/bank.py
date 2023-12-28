from datetime import datetime
from mongoengine import ( Document,
                          StringField,
                          FloatField,
                          DateTimeField,
                          ListField,
                          LazyReferenceField )

from helpers import helper

class Bank(Document):
    name = StringField(max_length=20)
    initial_balance = FloatField()
    current_balance = FloatField()
    total_disbursed_till_now = FloatField()
    expenses = ListField(LazyReferenceField('Expense'))
    created_at = DateTimeField(default=datetime.now().date())
    updated_at = DateTimeField(default=datetime.now().date())

    def __repr__(self):
        return f'<Bank:{self.name}>'

    @classmethod
    def get_banks(cls, **kwargs):
        banks = cls.objects
        if kwargs.get('name'):
            banks = banks.filter(name=kwargs['name'])
        if kwargs.get('id'):
            banks = banks.filter(id=kwargs['id'])

        return banks

    def get_expenses(self):
        all_expenses = [expense.fetch() for expense in self.expenses]
        return sorted(all_expenses, key=lambda e: e.created_at)

    def store_remaining_amount(self):
        sorted_expenses = self.get_expenses()
        for expense in sorted_expenses:
            self.update_bank_and_expense_data(expense)

    # TODO : write the below logic inside the workers.
    def update_bank_and_expense_data(self, expense, is_newly_created):
        expense_data_to_update = {}
        bank_data_to_update = {}
        if is_newly_created:
            remaining_amount_till_now = self.current_balance - expense.expense_total
            total_disbursed_till_now = self.total_disbursed_till_now + expense.expense_total

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
            expense_bank_current_balance = self.current_balance - expense.total_entry_entered

            expense_data_to_update.update(
                set__expense_total=(expense.expense_total + expense.total_entry_entered),
                set__remaining_amount_till_now=expense_bank_current_balance
            )
            bank_data_to_update.update(
                set__total_disbursed_till_now=(self.total_disbursed_till_now + expense.total_entry_entered),
                set__current_balance=expense_bank_current_balance,
            )

        expense.update(**expense_data_to_update)
        self.update(**bank_data_to_update)
        self.reload()

    def update_bank_data_after_expense_deletion(self, expense):
        current_balalnce = self.current_balance + expense.expense_total
        total_disbursed_till_now = self.total_disbursed_till_now - expense.expense_total
        self.update(
            set__total_disbursed_till_now=total_disbursed_till_now,
            set__current_balance=current_balalnce
        )
        self.reload()
