from src.utils.urls import URLS
from src.resources.auth_resource.views import UserLoginResource, UserRegisterResource
from src.resources.banks_resource.views import BanksResource, BanksDetailsResource
from src.resources.expenses_resource.views import ExpensesResource
from src.resources.expense_entry_tags_resource.views import ExpenseEntryTagResource

urls = [
    # login, register
    URLS(UserLoginResource, ["user/login"], name="user_login_API"),
    URLS(UserRegisterResource, ["user/register"], name="user_register_API"),
    # banks resource
    URLS(BanksResource, ["banks"], name="banks_resource_API"),
    URLS(BanksDetailsResource, ["banks/<string:bank_id>"], name="banks_details_resource_API"),
    # expenses resource
    URLS(ExpensesResource, ["expenses"], name="expenses_resource_API"),
    # expense entry tags
    URLS(ExpenseEntryTagResource, ["entry-tags"], name="expense_entry_tags_resource_API"),
]
