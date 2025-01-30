import pytest, json
from hamcrest import is_, assert_that

# src imports
from src.models.expense_entry_tag import ExpenseEntryTag

# tests imports
from tests.factories.user import UserFactory
from tests.functional.helper.helper import ExpenseEntryTagsHelper


class TestGetTags:

    @pytest.fixture(autouse=True)
    def setup(self, testapp, api_token):
        self.testapp = testapp
        self.api_token = api_token
        self.entry_tags_helper = ExpenseEntryTagsHelper(testapp)

        # save the default user
        self.user = UserFactory.get_user()
        self.user.save()

    def test_delete_tag_by_id(self):
        ee_tag = ExpenseEntryTag(name=f"Tag_789", user_id=self.user.id)
        ee_tag.save()

        payload = {"_id": str(ee_tag.id)}

        response = self.entry_tags_helper.delete_entry_tags_api_call(
            self.api_token, params=json.dumps(payload)
        )
        assert_that(response.status_code, is_(200))
        assert_that(response.json["success"], is_("Tag deleted successfully"))

    def test_delete_tag_by_not_providing_id(self):
        ee_tag = ExpenseEntryTag(name=f"Tag_789", user_id=self.user.id)
        ee_tag.save()

        payload = {"_id": None}

        response = self.entry_tags_helper.delete_entry_tags_api_call(
            self.api_token, params=payload
        )
        assert_that(response.status_code, is_(400))
        assert_that(response.json["error"], is_("Tag not found"))
