"""Public errors shared by the client and REST API."""


class FotmobError(Exception):
    code = "UPSTREAM_ERROR"
    status = 502

    def __init__(self, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class NotFoundError(FotmobError):
    code = "NOT_FOUND"
    status = 404


class RateLimitError(FotmobError):
    code = "RATE_LIMITED"
    status = 429


class AccessDeniedError(FotmobError):
    code = "ACCESS_DENIED"
    status = 502


class RequestTimeoutError(FotmobError):
    code = "TIMEOUT"
    status = 504


class InvalidResponseError(FotmobError):
    code = "INVALID_RESPONSE"


class NetworkError(FotmobError):
    code = "NETWORK_ERROR"


class APIError(FotmobError):
    code = "UPSTREAM_ERROR"
