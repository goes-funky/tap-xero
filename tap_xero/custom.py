import requests
from singer import Catalog

from tap_xero.client_utils import raise_for_error


class XeroCatalog(Catalog):
    def __init__(self, streams=None):
        if streams is None:
            streams = []
        super().__init__(streams)


def refresh_token(config: dict, session: requests.Session = None) -> dict:
    from base64 import b64encode

    header_token = b64encode(
        (config["client_id"] + ":" + config["client_secret"]).encode("utf-8")
    )

    headers = {
        "Authorization": "Basic " + header_token.decode("utf-8"),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    post_body = {
        "grant_type": "refresh_token",
        "refresh_token": config["refresh_token"],
    }

    session_ = session if session else requests.Session()

    response = session_.post(
        "https://identity.xero.com/connect/token", headers=headers, data=post_body
    )

    if response.status_code != 200:
        raise_for_error(response)
    else:
        response = response.json()

    return response


def write_secrets(config: dict) -> None:
    import sys
    import json

    secrets = {
        "type": "CREDENTIALS_CHANGED",
        "secrets": {
            "access_token": config["access_token"],
            "refresh_token": config["refresh_token"],
            "token_type": "bearer",
        },
    }
    message = json.dumps(secrets)
    sys.stdout.write(message)
    sys.stdout.flush()
