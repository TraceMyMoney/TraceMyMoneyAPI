import pytest, json
from hamcrest import is_, assert_that

# tests imports
from tests.factories.user import UserFactory
from tests.functional.helper.helper import ExpenseEntryTagsHelper


class TestCreateTags:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.entry_tags_helper = ExpenseEntryTagsHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def test_create_entry_tags(self):
        payload = {"name": "Test Tag"}
        response = self.entry_tags_helper.create_entry_tags_api_call(
            self.api_token, json.dumps(payload)
        )
        assert_that(response.status_code, is_(200))

    def test_create_entry_tags_which_already_exists(self):
        # Create the new tag
        payload = {"name": "Test Tag"}
        response = self.entry_tags_helper.create_entry_tags_api_call(
            self.api_token, json.dumps(payload)
        )
        assert_that(response.status_code, is_(200))

        # Create the same tag again
        payload = {"name": "Test Tag"}
        response = self.entry_tags_helper.create_entry_tags_api_call(
            self.api_token, json.dumps(payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(response.json["error"], is_("Tag already exists"))

    def test_create_entry_tags_without_passing_name(self):
        # Create the new tag
        payload = {}
        response = self.entry_tags_helper.create_entry_tags_api_call(
            self.api_token, json.dumps(payload)
        )
        assert_that(response.status_code, is_(400))
        assert_that(response.json["error"], is_("Please provide the name"))
