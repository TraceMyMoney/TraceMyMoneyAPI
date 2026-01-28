from flask_restful import Api
from flask_cors import CORS

from src.base import urls


def restful_app(app) -> None:
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
    api = Api(app, prefix="/")
    for url in urls:
        url.resource.method_decorators = (
            url.resource.base_decorators if hasattr(url.resource, "base_decorators") else []
        )
        api.add_resource(url.resource, *url.endpoint, endpoint=url.name, strict_slashes=False)
