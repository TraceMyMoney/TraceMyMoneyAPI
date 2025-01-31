from flask import current_app as app
from flask_apispec import MethodResource
from flask_restful import Resource

from src_restful.utils.exception import exception_handle


class BaseResource(MethodResource, Resource):
    base_decorators = [exception_handle]

    def __init__(self):
        app.logger.info("In the constructor of {}".format(self.__class__.__name__))
