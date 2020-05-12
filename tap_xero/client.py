import json
import base64
import decimal
import singer
from os.path import join
import re
from datetime import datetime, date, time
import requests
import xero.utils
from singer.utils import strftime
import six
import pytz


BASE_URL = "https://api.xero.com/api.xro/2.0"


LOGGER = singer.get_logger()


class XeroUnauthorized(Exception):
    pass


def _json_load_object_hook(_dict):
    """Hook for json.parse(...) to parse Xero date formats."""
    # This was taken from the pyxero library and modified
    # to format the dates according to RFC3339
    for key, value in _dict.items():
        if isinstance(value, six.string_types):
            value = xero.utils.parse_date(value)
            if value:
                if type(value) == date:
                    value = datetime.combine(value, time.min)
                value = value.replace(tzinfo=pytz.UTC)
                _dict[key] = strftime(value)
    return _dict


class XeroClient(object):
    def __init__(self, config, config_path):
        self.session = requests.Session()
        self.user_agent = config.get("user_agent")
        self.config_path = config_path
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.refresh_token = config['refresh_token']
        self.access_token = config['access_token']

        self.refresh()
        # Ensure credentials are valid
        self.filter("currencies")

    def refresh(self):
        LOGGER.info("Refreshing credentials")

        auth_token = self.client_id + ':' + self.client_secret

        headers = {
            'Authorization': "Basic " + base64.b64encode(auth_token.encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        url = "https://identity.xero.com/connect/token"

        body = 'grant_type=refresh_token&refresh_token={}'.format(self.refresh_token)
        request = requests.Request("POST", url, headers=headers, data=body)
        response = self.session.send(request.prepare())

        response = response.json()

        LOGGER.info(response)
        # Update local copies
        self.access_token = response['access_token']
        self.refresh_token = response['refresh_token']

        # Update config on filesystem
        self.write_config()

        return

    def write_config(self):
        # Update config at config_path
        with open(self.config_path) as file:
            config = json.load(file)

        config['refresh_token'] = self.refresh_token
        config['access_token'] = self.access_token

        with open(self.config_path, 'w') as file:
            json.dump(config, file, indent=2)
        
    def filter(self, tap_stream_id, *args, since=None, **params):
        xero_resource_name = tap_stream_id.title().replace("_", "")
        url = join(BASE_URL, xero_resource_name)
        headers = {"Accept": "application/json"}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if since:
            headers["If-Modified-Since"] = since

        headers['Authorization'] = 'Bearer ' + self.access_token
        import ipdb; ipdb.set_trace()
        1+1
        headers['Xero-tenant-id'] = foo
        
        request = requests.Request("GET", url, headers=headers, params=params)
        response = self.session.send(request.prepare())
        if response.status_code == 401:
            raise XeroUnauthorized(response)
        response.raise_for_status()
        response_meta = json.loads(response.text,
                                   object_hook=_json_load_object_hook,
                                   parse_float=decimal.Decimal)
        response_body = response_meta.pop(xero_resource_name)
        return response_body

    def get_tenants(self):
        """
        Get the list of tenants (Xero Organisations) to which this token grants access.
        """
        url = 'https://api.xero.com/connections'

        headers = {'Authorization': 'Bearer ' + self.access_token,
                   'Content-Type': 'application/json'}

        response = requests.get(url, headers=self.headers)

        response.raise_for_status()
        return response.json()
