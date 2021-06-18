from requests import Response


class XeroError(Exception):
    def __init__(self, message: str = None, response: Response = None):
        super().__init__(message)
        self.message = message
        self.response = response


class XeroBadRequestError(XeroError):
    pass


class XeroUnauthorizedError(XeroError):
    pass


class XeroForbiddenError(XeroError):
    pass


class XeroNotFoundError(XeroError):
    pass


class XeroPreConditionFailedError(XeroError):
    pass


class XeroTooManyError(XeroError):
    pass


class XeroTooManyInMinuteError(XeroError):
    pass


class XeroInternalError(XeroError):
    pass


class XeroNotImplementedError(XeroError):
    pass


class XeroNotAvailableError(XeroError):
    pass


ERROR_CODE_EXCEPTION_MAPPING = {
    400: {
        "raise_exception": XeroBadRequestError,
        "message": "A validation exception has occurred."
    },
    401: {
        "raise_exception": XeroUnauthorizedError,
        "message": "Invalid authorization credentials."
    },
    403: {
        "raise_exception": XeroForbiddenError,
        "message": "User doesn't have permission to access the resource."
    },
    404: {
        "raise_exception": XeroNotFoundError,
        "message": "The resource you have specified cannot be found."
    },
    412: {
        "raise_exception": XeroPreConditionFailedError,
        "message": "One or more conditions given in the request header fields were invalid."
    },
    429: {
        "raise_exception": XeroTooManyError,
        "message": "The API rate limit for your organisation/application pairing has been exceeded"
    },
    500: {
        "raise_exception": XeroInternalError,
        "message": "An unhandled error with the Xero API. Contact the Xero API team if problems persist."
    },
    501: {
        "raise_exception": XeroNotImplementedError,
        "message": "The method you have called has not been implemented."
    },
    503: {
        "raise_exception": XeroNotAvailableError,
        "message": "API service is currently unavailable."
    }
}
