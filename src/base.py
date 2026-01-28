from src.utils.urls import URLS
from src.auth_resource.views import UserLoginResource, UserRegisterResource

urls = [
    URLS(UserLoginResource, ["user/login"], name="user_login_API"),
    URLS(UserRegisterResource, ["user/register"], name="user_register_API"),
]
