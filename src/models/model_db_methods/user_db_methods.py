from src.models.bank import Bank
from src.models.expense import Expense
from src.models.expense_entry_tag import ExpenseEntryTag


def calculate_aggregated_data_with_daterange(subscribed_users, start_date, end_date):
    user_wise_aggregated_data = {}
    mapped_users = {
        user.id: {
            "banks": {bank.id: bank.name for bank in Bank.get_banks(user)},
            "tags": {
                str(tag["id"]): tag["name"] for tag in ExpenseEntryTag.get_tags(user)
            },
        }
        for user in subscribed_users
    }
    aggregated_report_data = Expense.get_report_data(
        list(mapped_users.keys()), start_date, end_date
    )

    for data in aggregated_report_data:
        user_id = data["_id"]["user_id"]
        bank_id = data["_id"]["bank_id"]
        tag_id = data["_id"]["entry_tags"]

        bank_name = mapped_users[user_id]["banks"][bank_id]
        tag_name = mapped_users[user_id]["tags"][tag_id]

        user = user_wise_aggregated_data.setdefault(str(user_id), {})
        bank = user.setdefault(bank_name, {})
        day = bank.setdefault(data["_id"]["created_at"].strftime("%A"), {})
        day[tag_name] = data["tags_wise_summation"]

    return user_wise_aggregated_data
