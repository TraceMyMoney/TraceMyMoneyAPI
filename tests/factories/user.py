# src imports
from src.models.user import User

# tests imports
from tests.constants import (
    TEST_USER_NAME,
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    TEST_USER_ID,
)


class UserFactory:

    @staticmethod
    def get_user(
        _id=TEST_USER_ID,
        username=TEST_USER_NAME,
        email=TEST_USER_EMAIL,
        password=TEST_USER_PASSWORD,
    ):
        return User(id=_id, username=username, email=email, password=password)
