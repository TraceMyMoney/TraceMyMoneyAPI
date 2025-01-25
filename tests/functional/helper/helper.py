class ExpenseHelper:
    def __init__(self, app):
        self.testapp = app

    def get_expenses_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/expenses/", headers=headers, params=params, expect_errors=True
        )

    def create_expense_api(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/expenses/create", headers=headers, params=params, expect_errors=True
        )

    def create_expense_entry_api(self, api_token, expense_id, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.patch(
            f"/expenses/add-entry?id={expense_id}",
            headers=headers,
            params=params,
            expect_errors=True,
        )

    def delete_expense_api(self, api_token, expense_id, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.delete(
            f"/expenses/delete?id={expense_id}",
            headers=headers,
            params=params,
            expect_errors=True,
        )

    def delete_expense_entry_api(self, api_token, expense_id, ee_id, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.delete(
            f"/expenses/delete-entry?id={expense_id}&ee_id={ee_id}",
            headers=headers,
            params=params,
            expect_errors=True,
        )

    def update_expense_entry_api(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.patch(
            f"/expenses/update-entry",
            headers=headers,
            params=params,
            expect_errors=True,
        )


class BanksHelper:
    def __init__(self, app):
        self.testapp = app

    def get_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.get(
            "/banks/", headers=headers, params=params, expect_errors=True
        )

    def post_banks_api_call(self, api_token, params={}):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.post(
            "/banks/create", headers=headers, params=params, expect_errors=True
        )

    def delete_banks_api_call(self, api_token, bank_id):
        headers = {
            "x-access-token": api_token,
            "Content-Type": "application/json",
        }
        return self.testapp.delete(
            f"/banks/delete?bank_id={bank_id}",
            headers=headers,
            params={},
            expect_errors=True,
        )
