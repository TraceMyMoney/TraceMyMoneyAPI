import random, sys, os
from mongoengine import connect, disconnect
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.models.user import User
from src.models.bank import Bank
from src.models.expense import Expense
from src.models.expense_entry_tag import ExpenseEntryTag

MONGO_DATABASE_URI = "mongodb+srv://parimalm4653:b9cIUcPqrd3fy8Dq@trackmoneyapi.1jzih.mongodb.net"
MONGO_DATABASE = "trackmoney_api"


disconnect()
connect(MONGO_DATABASE, host=MONGO_DATABASE_URI)
user = User(username="test123", email="test@gmail.com", password="test")
user.save()
print(f"SUCCESS : {user.username}")



bank = Bank(
    name="TEST 2",
    initial_balance=100000,
    current_balance=100000,
    user_id=user.id,
    total_disbursed_till_now=0,
)
bank.save()
print(f"SUCCESS : {bank.name}")

entry_tags = ["Transportation", "Groceries", "Clothing", "Entertainment", "Emergency fund", "Tracking expenses",
            "Groceries", "Coffee", "Gas", "Public transport", "Online subscription", "Takeout food", "Pharmacy",
            "Snacks", "Parking fee", "Household items", "Gym membership", "Streaming service", "Work lunch",
            "Mobile recharge", "Impulse shopping", "Pet supplies", "Laundry", "Weekend outing", "Office supplies",
            "Book purchase", "Petrol", "Petrol", "Petrol", "Petrol", "salary credited"]

for item in entry_tags:
    ee = ExpenseEntryTag(name=item, user_id=user.id).save()
    print(f"SUCCESS : {ee.name}")

mapped_entry_tags = dict(
    map(lambda x: (x.name, str(x.id)), ExpenseEntryTag.objects(user_id=user.id))
)

days_per_month_2024 = [(1, 31), (2, 29), (3, 31), (4, 30), (5, 31), (6, 30),
                        (7, 31), (8, 31), (9, 30), (10, 31), (11, 30), (12, 31)]

for month, days in days_per_month_2024:
    print(f"MONTH: {month}")
    for day in range(1, days + 1):
        print(f"MONTH: {month}, DAY: {day}")
        is_salary_day = day == days

        expense_payload = {
            "bank": bank.id,
            "user_id": user.id,
            "created_at": datetime(2024, month, day),
            "expenses": [
                {
                    "amount": -50000 if is_salary_day else random.randint(1, 3000),
                    "description": (
                        "Salary credited"
                        if is_salary_day
                        else (random_entry_tag := random.choices([tag for tag in entry_tags if tag != "salary credited"])[0])
                    ),
                    "entry_tags": [
                        (
                            mapped_entry_tags["salary credited"]
                            if is_salary_day
                            else mapped_entry_tags[random_entry_tag]
                        )
                    ],
                },
            ],
        }
        Expense(**expense_payload).save()
