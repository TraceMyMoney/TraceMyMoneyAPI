from calendar import timegm
from datetime import datetime
from functools import wraps
from typing import Callable, Any, Tuple

from flask import current_app as app
from flask_jwt_extended.exceptions import (
    InvalidHeaderError,
    RevokedTokenError,
    NoAuthorizationError,
)
from flask_restful import abort
from jwt import ExpiredSignatureError, DecodeError, InvalidTokenError
from marshmallow import ValidationError
from werkzeug.exceptions import UnprocessableEntity, BadRequest


class AuthorizationException(Exception):
    pass


class AuthenticationException(Exception):
    pass


class ValueErrorWithoutNotification(Exception):
    pass


class ValidationError(Exception):
    pass


class EntryTagExistsError(Exception):
    pass


def exception_handle(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Tuple[Any, int]:
        try:
            return fn(*args, **kwargs)
        except ValueError as val_err:
            app.logger.error(val_err)

            return abort(400, error=str(val_err))
        except ValueErrorWithoutNotification as val_err:
            app.logger.warning(val_err)

            return abort(400, error=str(val_err))
        except EntryTagExistsError as val_err:
            app.logger.warning(val_err)

            return abort(400, error=str(val_err))
        except KeyError as key_err:
            app.logger.error(key_err)

            return abort(400, error=str(key_err))
        except IOError as io_err:
            app.logger.error(str(io_err))

            return abort(403, error=str(io_err))
        except AuthenticationException as e:
            app.logger.warning(str(e))

            return abort(401, error=str(e))
        except AuthorizationException as e:
            app.logger.warning(str(e))

            return abort(403, error=str(e))
        except ValidationError as e:
            app.logger.error(str(e))

            return abort(400, error=e.messages)
        except UnprocessableEntity as e:
            app.logger.error(str(e))

            if e.data and e.data.get("messages"):  # type: ignore
                return abort(400, error=e.data.get("messages"))  # type: ignore
            return abort(400, error=str(e.messages))  # type: ignore
        except (BadRequest, InvalidHeaderError) as e:
            app.logger.error(str(e))

            return abort(400, error=e.description)
        except (RevokedTokenError, NoAuthorizationError) as exc:
            app.logger.warn(exc)

            return abort(401, message=str(exc))
        except ExpiredSignatureError as e:
            app.logger.error(e)
            app.logger.error(f"now: {timegm(datetime.utcnow().utctimetuple())}")

            return abort(401, error="Session has expired, please re-login")
        except InvalidTokenError as e:
            app.logger.error(e)
            return abort(401, error="Incorrect token provided")
        except Exception as exc:
            app.logger.error(exc)

            return abort(500, error=str(exc))

    return wrapper
