from src.models.user import User
from src.models.model_db_methods.user_db_methods import (
    calculate_aggregated_data_with_daterange,
)


def get_expenses_data(start_date, end_date):
    subscribed_users = User.objects(is_subscribed_to_emails=True).only("id")
    aggregated_data = calculate_aggregated_data_with_daterange(
        subscribed_users, start_date, end_date
    )
    return aggregated_data
