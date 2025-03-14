# libraries import
import pytest
import jwt
from flask_webtest import TestApp
from datetime import datetime, timedelta
from flask_jwt_extended import create_access_token


# imports from src
from src.extensions import connect_mongo
from src.main import create_app
from src.extensions import config

# imports from tests
from tests.constants import TEST_USER_ID, TEST_USER_NAME, TEST_FAKE_USER_ID


@pytest.fixture(autouse=True, scope="session")
def setup_db():
    mongo_engine = connect_mongo()
    mongo_engine.drop_database(config["MONGO_DATABASE"])


@pytest.fixture(autouse=True)
def drop_db():
    yield
    mongo_engine = connect_mongo()
    mongo_engine.drop_database(config["MONGO_DATABASE"])


@pytest.fixture(scope="session")
def app():
    _app = create_app()
    with _app.app_context():
        yield _app


@pytest.fixture(scope="session")
def testapp(app):
    return TestApp(app)


@pytest.fixture
def api_token():
    return jwt.encode(
        {
            "user_id": str(TEST_USER_ID),
            "user_name": TEST_USER_NAME,
            "exp": datetime.utcnow() + timedelta(minutes=30),
        },
        config.get("JWT_SECRET_KEY"),
    )


@pytest.fixture
def jwt_token():
    return jwt.encode(
        {
            "user_id": str(TEST_FAKE_USER_ID),
            "user_name": TEST_USER_NAME,
            "exp": datetime.utcnow() + timedelta(minutes=30),
        },
        config.get("JWT_SECRET_KEY"),
    )
