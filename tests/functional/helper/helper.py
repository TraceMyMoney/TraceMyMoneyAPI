class BaseHelper:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
        }


class ExpenseHelper(BaseHelper):
    def __init__(self, app):
        super().__init__()
        self.testapp = app

    def get_expenses_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.get(
            "/expenses/", headers=self.headers, params=params, expect_errors=True
        )

    def create_expense_api(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.post(
            "/expenses/create", headers=self.headers, params=params, expect_errors=True
        )

    def create_expense_entry_api(self, api_token, expense_id, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.patch(
            f"/expenses/add-entry?id={expense_id}",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )

    def delete_expense_api(self, api_token, expense_id, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.delete(
            f"/expenses/delete?id={expense_id}",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )

    def delete_expense_entry_api(self, api_token, expense_id, ee_id, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.delete(
            f"/expenses/delete-entry?id={expense_id}&ee_id={ee_id}",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )

    def update_expense_entry_api(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.patch(
            f"/expenses/update-entry",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )


class BanksHelper(BaseHelper):
    def __init__(self, app):
        super().__init__()
        self.testapp = app

    def get_banks_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.get(
            "/banks/", headers=self.headers, params=params, expect_errors=True
        )

    def post_banks_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.post(
            "/banks/create", headers=self.headers, params=params, expect_errors=True
        )

    def delete_banks_api_call(self, api_token, bank_id):
        self.headers["x-access-token"] = api_token
        return self.testapp.delete(
            f"/banks/delete?bank_id={bank_id}",
            headers=self.headers,
            params={},
            expect_errors=True,
        )


class ExpenseEntryTagsHelper(BaseHelper):
    def __init__(self, app):
        super().__init__()
        self.testapp = app

    def get_entry_tags_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.get(
            "/entry-tags/", headers=self.headers, params=params, expect_errors=True
        )

    def create_entry_tags_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.post(
            "/entry-tags/create",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )

    def delete_entry_tags_api_call(self, api_token, params={}):
        self.headers["x-access-token"] = api_token
        return self.testapp.delete(
            "/entry-tags/delete",
            headers=self.headers,
            params=params,
            expect_errors=True,
        )
