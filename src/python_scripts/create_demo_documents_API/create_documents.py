from . import make_request

import random

AUTH_TOKEN = None

def register_user():
    payload = {
        "username": "testuser",
        "email": "test@gmail.com",
        "password": "test"
    }
    res = make_request("register", method="POST", data=payload)
    if res.status_code == 201:
        print("User created successfully")
    else:
        print("Error while creating the user")
        print(f"ERROR : {res.json()}")

def login_user():
    payload = {
        "username": "testuser",
        "password": "test"
    }
    res = make_request("login", method="POST", data=payload)
    if res.status_code == 200:
        if response_data := res.json():
            return response_data["token"]
    else:
        print("ERROR while login")
        print(f"ERROR : {res.json()}")
        return None

class CreateDocuments:

    def __init__(self, auth_token):
      self.AUTH_TOKEN = auth_token

    def create_bank(self):
      payload = {
        "name": "TEST 2",
        "initial_balance": 100000,
        "current_balance": 100000,
        "total_disbursed_till_now": 0
      }
      res = make_request(
          "banks/create",
          method="POST",
          data=payload,
          auth_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjc5MzBjYTk3OTc1NDM1NTI1N2FkMDMyIiwidXNlcl9uYW1lIjoidGVzdHVzZXIiLCJleHAiOjE3Mzc2OTcxMjZ9.5cJjpJkT-tFJfPS7IBysXtIfGXAYfjFAKoYHLsn8__A"
      )

    def create_expenses(self):
tag_dict_map = {
  'Petrol': '6793107b79754355257ad125',
  'Bike Servicing': '6793107b79754355257ad126',
  'Breakfast': '6793107b79754355257ad127',
  'Clothing': '6793107b79754355257ad128',
  'Entertainment': '6793107b79754355257ad129',
  'Food Expenses': '6793107b79754355257ad12a',
  'Transportation': '6793107b79754355257ad12b',
  'Pets': '6793107b79754355257ad12c',
  'Housing': '6793107b79754355257ad12d',
  'Healthcare': '6793107b79754355257ad12e',
  'Utilities': '6793107b79754355257ad12f',
  'Insurance': '6793107b79754355257ad130',
}

for i in range(1, 32):
  payload = {
    "bank_id": "6793206a79754355257ad1ac",
    "created_at": f"{i}-10-2024 00:00",
    "expenses": []
  }

  for i in range(1, 4):
    random_choice = random.choice(['Petrol', 'Bike Servicing', 'Breakfast', 'Clothing', 'Entertainment', 'Food Expenses', 'Transportation', 'Pets', 'Housing', 'Healthcare', 'Utilities', 'Insurance'])
    choice = tag_dict_map[random_choice]
    payload["expenses"].append({
      "amount": random.randint(1, 1000),
      "description": random_choice,
      "selected_tags": [choice]
    })

  res = make_request(
    "expenses/create",
    method="POST",
    data=payload,
    auth_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjc5MzBjYTk3OTc1NDM1NTI1N2FkMDMyIiwidXNlcl9uYW1lIjoidGVzdHVzZXIiLCJleHAiOjE3Mzc2OTcyMTd9.S0veOM_LXXwUJiEwSkRoLJ5ZBt2UTzu3h9_O8wOLvlk"
  )


def create_tags():
   tag_list = ['Petrol', 'Bike Servicing', 'Breakfast', 'Clothing', 'Entertainment', 'Food Expenses', 'Transportation', 'Pets', 'Housing', 'Healthcare', 'Utilities', 'Insurance']
   for i in tag_list:
      payload = {
         "name": i
      }
      res = make_request(
          "entry-tags/create",
          method="POST",
          data=payload,
          auth_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjc5MzBjYTk3OTc1NDM1NTI1N2FkMDMyIiwidXNlcl9uYW1lIjoidGVzdHVzZXIiLCJleHAiOjE3Mzc2OTIwOTJ9.Xc6-J0Edpvjijon-gbjaxkVVAyMNQ8GS3GX7lUBqLFA"
      )



