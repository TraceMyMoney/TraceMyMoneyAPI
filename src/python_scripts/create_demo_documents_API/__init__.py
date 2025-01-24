import requests

session = requests.Session()
session.base_url = "http://127.0.0.1:5000/"


def make_request(endpoint, method="GET", params=None, data=None, auth_token=None):
    url = session.base_url + endpoint
    session.headers.update({
        "Content-Type": "application/json",
    })
    if auth_token:
        session.headers.update({
            "x-access-token": auth_token,
        })
    response = session.request(method, url, params=params, json=data)
    return response
