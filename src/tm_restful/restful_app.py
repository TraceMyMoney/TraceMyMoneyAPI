from flask_cors import CORS
from flask_restful import Api

from src.tm_restful.routes import ROUTE_LIST


def restful_app(app):
    CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
    api = Api(app, prefix="/")

    for url in ROUTE_LIST:
        url.resource.method_decorators = (
            (url.resource.decorators or []) + url.resource.base_decorators
            if hasattr(url.resource, "base_decorators")
            else []
        )
        api.add_resource(
            url.resource,
            *url.endpoint,
            endpoint=url.resource.__name__.lower(),
            strict_slashes=False
        )
