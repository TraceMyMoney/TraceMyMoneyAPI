from mongoengine import signals
from models.expense import Expense

def pre_save_expense(sender, document, **kwargs):
    __set_expense_field(document)

def pre_bulk_insert_data(sender, documents, **kwargs):
    for document in documents:
        __set_expense_field(document)

def __set_expense_field(document):
    document.expense_total = document.get_total_of_expenses()
    document.day = document.created_at.strftime('%A')
    expense_bank = document.get_bank() # lazy loading
    if expense_bank:
        document.bank_name = expense_bank.name

    return document

signals.pre_save.connect(pre_save_expense, sender=Expense)
signals.pre_bulk_insert.connect(pre_bulk_insert_data, sender=Expense)
