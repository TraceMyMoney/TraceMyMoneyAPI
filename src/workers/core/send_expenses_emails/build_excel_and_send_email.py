import xlsxwriter

from src.models.model_db_methods.user_db_methods import UserDBMethods


def build_excel_and_send_email_task(self, data, exchange=None):
    start_date = data.pop("start_date")
    end_date = data.pop("end_date")

    for user_id, aggregated_data in data.items():
        if (user := UserDBMethods.get_record_with_id(user_id)) and (
            user_email := user.email
        ):
            built_excel_book = build_excel_with_provided_data(
                aggregated_data, start_date, end_date
            )
            send_email_to_user(user_email, built_excel_book)


def build_excel_with_provided_data(aggregated_data, start_date, end_date):
    aggregated_data = {
        "SBI": {
            "Rikshaw or Cab (OLA or Uber)": 114.0,
            "Hot Drinks": 30.0,
            "Things for me": 312.0,
            "Food": 613.0,
            "New House": 32.0,
            "Splits in friends": 880.0,
            "Milk": 37.0,
            "Junkfood": 145.0,
            "Entertainment": 510.0,
            "Online orders (Amazon, flipkart, etc)": 347.0,
            "wafors": 40.0,
            "Grocery": 125.0,
            "Gyn things": 85.0,
            "Hair cut, Beard": 60.0,
            "Devotion": 50.0,
            "Petrol": 205.0,
        },
        "CASH": {"Bike parking": 90.0, "One day trip ": 90.0},
        "HDFC": {
            "IPO Applied": 14910.0,
            "Salary Credited": 0,
            "Transfered to SBI": 7000.0,
            "New House money returned": 59000.0,
            "New House": 164901.0,
        },
    }

    workbook = xlsxwriter.Workbook(f"Daily Expenses from {start_date} to {end_date}")
    worksheet = workbook.add_worksheet()


def send_email_to_user(user_email, built_excel_book):
    pass
