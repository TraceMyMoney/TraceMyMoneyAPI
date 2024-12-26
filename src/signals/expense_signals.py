# libraries imports
from mongoengine import signals

# relative imports
from src.models.expense import Expense
from src.workers.update_bank_and_expense_data_worker import update_bank_and_expense_data


def pre_save_expense(sender, document, **kwargs):
    # Don't do any calculations here at all cost
    # Just do the prior assignments
    __set_expense_field(document)


def pre_bulk_insert_data(sender, documents, **kwargs):
    for document in documents:
        __set_expense_field(document)


def post_save_expense(sender, document, **kwargs):
    if hasattr(document, "removed_entry_record_amount"):
        total_entry_entered = 0 - document.removed_entry_record_amount
    else:
        total_entry_entered = getattr(document, "total_entry_entered", None)

    expense_bank = document.get_bank()  # lazy loading
    if expense_bank:
        update_bank_and_expense_data.delay(
            bank_id=str(expense_bank.id),
            expense_id=str(document.id),
            is_newly_created=kwargs.get("created"),
            total_entry_entered=total_entry_entered,
            user_id=str(document.user_id),
        )


def post_bulk_insert_data(sender, documents, **kwargs):
    for document in documents:
        # TODO: redis caching, optimization
        expense_bank = document.get_bank()  # lazy loading
        if expense_bank:
            update_bank_and_expense_data.delay(
                bank_id=str(expense_bank.id),
                expense_id=str(document.id),
                is_newly_created=True,
                total_entry_entered=getattr(document, "total_entry_entered", None),
                user_id=str(document.user_id),
            )


def post_delete_expense(sender, document, **kwargs):
    expense_bank = document.get_bank()  # lazy loading
    # After removing the specified expense, it's necessary to include its total in the
    # remaining_amount_till_now for the records whose creation time greater that of the given document.
    if expenses := Expense.objects(created_at__gte=document.created_at):
        expenses.update(inc__remaining_amount_till_now=document.expense_total)
    if expense_bank:
        expense_bank.update_bank_data_after_expense_deletion(document)

    return document


def __set_expense_field(document):
    document.expense_total = document.get_total_of_expenses()
    document.day = document.created_at.strftime("%A")
    expense_bank = document.get_bank()  # lazy loading
    if expense_bank:
        document.bank_name = expense_bank.name

    return document


signals.pre_save.connect(pre_save_expense, sender=Expense)
signals.pre_bulk_insert.connect(pre_bulk_insert_data, sender=Expense)
signals.post_save.connect(post_save_expense, sender=Expense)
signals.post_bulk_insert.connect(post_bulk_insert_data, sender=Expense)
signals.post_delete.connect(post_delete_expense, sender=Expense)
