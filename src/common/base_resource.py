from flask_restful import Resource

from src.utils.resource_exceptions import exception_handle


class BaseResource(Resource):
    base_decorators = [exception_handle]
