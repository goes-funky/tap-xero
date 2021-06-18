import decimal
import json
from base64 import b64encode
from os.path import join
from typing import Union, List

import backoff
import requests
import singer

from tap_xero.client_utils import retry_after_wait_gen, is_not_status_code_fn, raise_for_error, update_config_file, \
    _json_load_object_hook
from tap_xero.exceptions import XeroTooManyInMinuteError, XeroInternalError

LOGGER = singer.get_logger()

BASE_URL = "https://api.xero.com/api.xro/2.0"


class XeroClient:
    def __init__(self, config: dict) -> None:
        self.session = requests.Session()
        self.user_agent = config.get("user_agent")
        self.tenant_id = None
        self.access_token = None

    def refresh_credentials(self, config: dict, config_path: str) -> None:

        header_token = b64encode((config["client_id"] + ":" + config["client_secret"]).encode('utf-8'))

        headers = {
            "Authorization": "Basic " + header_token.decode('utf-8'),
            "Content-Type": "application/x-www-form-urlencoded"
        }

        post_body = {
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
        }
        resp = self.session.post("https://identity.xero.com/connect/token", headers=headers, data=post_body)

        if resp.status_code != 200:
            raise_for_error(resp)
        else:
            resp = resp.json()

            # Write to config file
            config['refresh_token'] = resp["refresh_token"]
            update_config_file(config, config_path)
            self.access_token = resp["access_token"]
            # self.tenant_id = config['tenant_id']

    @backoff.on_exception(backoff.expo, (json.decoder.JSONDecodeError, XeroInternalError), max_tries=3)
    @backoff.on_exception(retry_after_wait_gen, XeroTooManyInMinuteError, giveup=is_not_status_code_fn([429]),
                          jitter=None, max_tries=3)
    def check_platform_access(self, config: dict, config_path: str) -> None:

        # Validating the authentication of the provided configuration
        self.refresh_credentials(config, config_path)

        headers = {
            "Authorization": "Bearer " + self.access_token,
            "Xero-Tenant-Id": self.tenant_id,
            "Content-Type": "application/json"
        }

        # Validating the authorization of the provided configuration
        contacts_url = join(BASE_URL, "Contacts")
        request = requests.Request("GET", contacts_url, headers=headers)
        response = self.session.send(request.prepare())

        if response.status_code != 200:
            raise_for_error(response)

    @backoff.on_exception(backoff.expo, (json.decoder.JSONDecodeError, XeroInternalError), max_tries=3)
    @backoff.on_exception(retry_after_wait_gen, XeroTooManyInMinuteError, giveup=is_not_status_code_fn([429]),
                          max_tries=3)
    def filter(self, tap_stream_id: str, since=None, **params) -> Union[List[dict], None]:
        xero_resource_name = tap_stream_id.title().replace("_", "")
        url = join(BASE_URL, xero_resource_name)
        headers = {"Accept": "application/json",
                   "Authorization": "Bearer " + self.access_token,
                   "Xero-tenant-id": self.tenant_id}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if since:
            headers["If-Modified-Since"] = since

        request = requests.Request("GET", url, headers=headers, params=params)
        response = self.session.send(request.prepare())

        if response.status_code != 200:
            raise_for_error(response)
            return None
        else:
            response_meta = json.loads(response.text,
                                       object_hook=_json_load_object_hook,
                                       parse_float=decimal.Decimal)
            response_body = response_meta.pop(xero_resource_name)
            return response_body
