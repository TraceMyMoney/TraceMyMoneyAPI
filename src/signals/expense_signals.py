from mongoengine import signals
from models.expense import Expense

def pre_save_expense(sender, document, **kwargs):
    # Don't do any calculations here at all cost
    # Just do the prior assignments
    __set_expense_field(document)

def pre_bulk_insert_data(sender, documents, **kwargs):
    for document in documents:
        __set_expense_field(document)

def post_save_expense(sender, document, **kwargs):
    expense_bank = document.get_bank() # lazy loading
    if expense_bank:
        if kwargs.get('created'):
            expense_bank.update(push__expenses=document)
            expense_bank.update_bank_and_expense_data(document)
        else:
            # TODO : Optimize the following
            expense_bank_current_balance = expense_bank.current_balance - document.total_entry_entered
            expense_bank.update(
                set__total_disbursed_till_now=(expense_bank.total_disbursed_till_now + document.total_entry_entered),
                set__current_balance=expense_bank_current_balance,
            )
            document.update(
                set__expense_total=(document.expense_total + document.total_entry_entered),
                set__remaining_amount_till_now=expense_bank_current_balance
            )
            expense_bank.reload()

def post_bulk_insert_data(sender, documents, **kwargs):
    for document in documents:
       # TODO: redis caching
       expense_bank = document.get_bank() # lazy loading
       if expense_bank:
           expense_bank.update(push__expenses=document)

def post_delete_expense(sender, document, **kwargs):
    expense_bank = document.get_bank() # lazy loading
    if expense_bank:
        expense_bank.update_bank_data_after_expense_deletion(document)

    return document

def __set_expense_field(document):
    document.expense_total = document.get_total_of_expenses()
    document.day = document.created_at.strftime('%A')
    expense_bank = document.get_bank() # lazy loading
    if expense_bank:
        document.bank_name = expense_bank.name

    return document

signals.pre_save.connect(pre_save_expense, sender=Expense)
signals.pre_bulk_insert.connect(pre_bulk_insert_data, sender=Expense)
signals.post_save.connect(post_save_expense, sender=Expense)
signals.post_bulk_insert.connect(post_bulk_insert_data, sender=Expense)
signals.post_delete.connect(post_delete_expense, sender=Expense)
