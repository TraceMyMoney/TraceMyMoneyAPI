from functools import wraps
from flask import current_app as app
from webargs.flaskparser import abort
from werkzeug.exceptions import UnprocessableEntity
from mongoengine import NotUniqueError


class AuthorizationException(Exception):
    pass


def exception_handle(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)

        except ValueError as val_err:
            app.logger.error(val_err, exc_info=True)
            return abort(400, message=str(val_err))

        except UnprocessableEntity as e:
            messages = e.data["messages"]
            if "querystring" in messages:
                msg = messages.get("querystring")
            elif "form" in messages:
                msg = messages.get("form")
            else:
                msg = messages.get("json")
            return abort(400, message=str(msg))

        except NotUniqueError as err:
            return abort(400, message=str("Record already exists"))

        except AuthorizationException as e:
            return abort(401, message=str(e))

        except Exception as exc:
            app.logger.critical(exc)
            return abort(500, message=str(exc))

    return wrapper
