from src.utils.urls import URLS
from src.resources.auth_resource.views import UserLoginResource, UserRegisterResource
from src.resources.banks_resource.views import BanksResource, BanksDetailsResource

urls = [
    # login, register
    URLS(UserLoginResource, ["user/login"], name="user_login_API"),
    URLS(UserRegisterResource, ["user/register"], name="user_register_API"),
    # bank resource
    URLS(BanksResource, ["banks"], name="banks_resource_API"),
    URLS(BanksDetailsResource, ["banks/<string:bank_id>"], name="banks_details_resource_API"),
]
