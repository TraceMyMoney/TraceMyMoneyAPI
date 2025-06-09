from src.models.user_preference import UserPreference
from src.database import BaseMethods


class UserPreferenceDBMethods(BaseMethods):
    model = UserPreference
