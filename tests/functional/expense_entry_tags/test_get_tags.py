import pytest, random
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

    def test_get_all_tags(self):
        total_number_of_entry_tags = 15
        for i in range(total_number_of_entry_tags):
            ee_tag = ExpenseEntryTag(name=f"Tag_{i}", user_id=self.user.id)
            ee_tag.save()

        response = self.entry_tags_helper.get_entry_tags_api_call(self.api_token)
        assert_that(response.status_code, is_(200))
        assert_that(len(response.json["entry_tags"]), is_(total_number_of_entry_tags))
        for i in range(total_number_of_entry_tags):
            assert_that(response.json["entry_tags"][i]["name"], is_(f"Tag_{i}"))

    def test_get_tags_by_name_without_regex(self):
        total_number_of_entry_tags = 15
        for i in range(total_number_of_entry_tags):
            ee_tag = ExpenseEntryTag(name=f"Tag_{i}", user_id=self.user.id)
            ee_tag.save()
        payload = {"name": "Tag_1", "regex": False}
        response = self.entry_tags_helper.get_entry_tags_api_call(
            self.api_token, params=payload
        )
        assert_that(response.status_code, is_(200))
        assert_that(len(response.json["entry_tags"]), is_(1))
        assert_that(response.json["entry_tags"][0]["name"], is_("Tag_1"))

    def test_get_tags_by_name_with_regex(self):
        total_number_of_entry_tags = 15
        for i in range(total_number_of_entry_tags):
            ee_tag = ExpenseEntryTag(name=f"Tag_{i}", user_id=self.user.id)
            ee_tag.save()
        payload = {"name": "Tag_1", "regex": True}
        response = self.entry_tags_helper.get_entry_tags_api_call(
            self.api_token, params=payload
        )
        assert_that(response.status_code, is_(200))
        assert_that(len(response.json["entry_tags"]), is_(6))

        expected_tags_with_regex = [
            "Tag_1",
            "Tag_10",
            "Tag_11",
            "Tag_12",
            "Tag_13",
            "Tag_14",
        ]
        for index, item in zip(range(0, 7), expected_tags_with_regex):
            assert_that(response.json["entry_tags"][index]["name"], is_(item))

    def test_get_tags_by_id(self):
        ee_tag = ExpenseEntryTag(name="Tag_Test", user_id=self.user.id)
        ee_tag.save()

        payload = {"_id": str(ee_tag.id)}
        response = self.entry_tags_helper.get_entry_tags_api_call(
            self.api_token, params=payload
        )

        respone_entry_tag = response.json["entry_tags"][0]
        assert_that(response.status_code, is_(200))
        assert_that(respone_entry_tag["id"], is_(str(ee_tag.id)))
