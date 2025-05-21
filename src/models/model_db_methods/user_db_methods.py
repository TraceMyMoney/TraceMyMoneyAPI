from src.models.bank import Bank
from src.models.expense import Expense
from src.models.expense_entry_tag import ExpenseEntryTag

from datetime import datetime


def calculate_aggregated_data_with_daterange(subscribed_users, start_date, end_date):
    user_wise_aggregated_data = {}
    print(f"subscribed_users : {subscribed_users}")
    mapped_users = {
        user.id: {
            "banks": {bank.id: bank.name for bank in Bank.get_banks(user)},
            "tags": {
                str(tag["id"]): tag["name"] for tag in ExpenseEntryTag.get_tags(user)
            },
        }
        for user in subscribed_users
    }
    start_date = datetime.combine(datetime(2025, 1, 1).date(), datetime.min.time())
    end_date = datetime.combine(datetime(2025, 1, 1).date(), datetime.max.time())
    aggregated_report_data = Expense.get_report_data(
        list(mapped_users.keys()), start_date, end_date
    )
    """
        {
            "_id": {
                "entry_tags": "6773d630e31b98b2b89db32a",
                "user_id": ObjectId("676d8ba24b77cfc402f66ed0"),
                "created_at": datetime.datetime(2025, 3, 13, 0, 0),
                "bank_id": ObjectId("671f1224503ef386abbb841d"),
            },
            "tags_wise_summation": 620.0,
        }
    """
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
