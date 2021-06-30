import json
import math
import re
import sys
from datetime import datetime, date, time, timedelta
from typing import Generator, Callable, Union, List, MutableMapping, Optional

import pytz
import requests
import singer
import six
from requests import Response
from singer.utils import strftime, strptime_to_utc

from tap_xero.exceptions import (
    XeroError,
    ERROR_CODE_EXCEPTION_MAPPING,
    XeroTooManyInMinuteError,
)

LOGGER = singer.get_logger()


def parse_date(value: str) -> Union[datetime, None]:
    # Xero datetimes can be .NET JSON date strings which look like
    # "/Date(1419937200000+0000)/"
    # https://developer.xero.com/documentation/api/requests-and-responses
    pattern = r"Date\((\-?\d+)([-+])?(\d+)?\)"
    match = re.search(pattern, value)

    iso8601pattern = r"((\d{4})-([0-2]\d)-0?([0-3]\d)T([0-5]\d):([0-5]\d):([0-6]\d))"

    if not match:
        iso8601match = re.search(iso8601pattern, value)
        if iso8601match:
            try:
                return strptime_to_utc(value)
            except Exception:
                return None
        else:
            return None

    millis_timestamp, offset_sign, offset = match.groups()
    if offset:
        if offset_sign == "+":
            offset_sign = 1
        else:
            offset_sign = -1
        offset_hours = offset_sign * int(offset[:2])
        offset_minutes = offset_sign * int(offset[2:])
    else:
        offset_hours = 0
        offset_minutes = 0

    return datetime.utcfromtimestamp((int(millis_timestamp) / 1000)) + timedelta(
        hours=offset_hours, minutes=offset_minutes
    )


def _json_load_object_hook(_dict: dict) -> dict:
    """Hook for json.parse(...) to parse Xero date formats."""
    # This was taken from the pyxero library and modified
    # to format the dates according to RFC3339
    for key, value in _dict.items():
        if isinstance(value, six.string_types):
            value = parse_date(value)
            if value:
                # NB> Pylint disabled because, regardless of idioms, this is more explicit than isinstance.
                if type(value) is date:  # pylint: disable=unidiomatic-typecheck
                    value = datetime.combine(value, time.min)
                value = value.replace(tzinfo=pytz.UTC)
                _dict[key] = strftime(value)
    return _dict


def update_config_file(config: dict, config_path: str) -> None:
    with open(config_path, "w") as config_file:
        json.dump(config, config_file, indent=2)


def is_not_status_code_fn(status_code: List[int]) -> Callable:
    def gen_fn(exc) -> bool:
        if (
            getattr(exc, "response", None)
            and getattr(exc.response, "status_code", None)
            and exc.response.status_code not in status_code
        ):
            return True
        # Retry other errors up to the max
        return False

    return gen_fn


def retry_after_wait_gen() -> Generator[float, int, None]:
    """
    This is called in an except block so we can retrieve the exception and check it.
    The raised exception should be of type exceptions.XeroError and from that instance we get the response from request.
    """
    while True:
        # This is called in an except block so we can retrieve the exception
        # and check it.
        exc_info = sys.exc_info()
        exception_instance: Optional[XeroError, BaseException] = exc_info[1]
        if isinstance(exception_instance, XeroError):
            resp = exception_instance.response
            sleep_time_str = resp.headers.get("Retry-After")
            LOGGER.info(
                "API rate limit exceeded -- sleeping for %s seconds", sleep_time_str
            )
            yield math.floor(float(sleep_time_str))
        else:
            raise AttributeError("Exception does not have a response property.")


def raise_for_error(response: Response) -> None:
    try:
        response.raise_for_status()
    except (requests.HTTPError, requests.ConnectionError) as error:
        try:
            error_code: int = response.status_code

            # Handling status code 429 specially since the required information is present in the headers
            if error_code == 429:
                resp_headers: MutableMapping = response.headers
                api_rate_limit_message: str = ERROR_CODE_EXCEPTION_MAPPING[429][
                    "message"
                ]
                message: str = "HTTP-error-code: 429, Error: {}. Please retry after {} seconds".format(
                    api_rate_limit_message, resp_headers.get("Retry-After")
                )

                # Raise XeroTooManyInMinuteError exception if minute limit is reached
                if resp_headers.get("X-Rate-Limit-Problem") == "minute":
                    raise XeroTooManyInMinuteError(message, response) from None
            # Handling status code 403 specially since response of API does not contain enough information
            elif error_code in (403, 401):
                api_message = ERROR_CODE_EXCEPTION_MAPPING[error_code]["message"]
                message = "HTTP-error-code: {}, Error: {}".format(
                    error_code, api_message
                )
            else:
                # Forming a response message for raising custom exception
                try:
                    response_json = response.json()
                except Exception:
                    response_json = {}

                message = "HTTP-error-code: {}, Error: {}".format(
                    error_code,
                    response_json.get(
                        "error",
                        response_json.get(
                            "Title",
                            response_json.get(
                                "Detail",
                                ERROR_CODE_EXCEPTION_MAPPING.get(error_code, {}).get(
                                    "message", "Unknown Error"
                                ),
                            ),
                        ),
                    ),
                )

            exc = ERROR_CODE_EXCEPTION_MAPPING.get(error_code, {}).get(
                "raise_exception", XeroError
            )
            raise exc(message, response) from None

        except (ValueError, TypeError):
            raise XeroError(error) from None
