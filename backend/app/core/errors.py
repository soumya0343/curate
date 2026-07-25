class AppError(Exception):
    code = "INTERNAL"
    retryable = False
    http_status = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def envelope(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "retryable": self.retryable}}


class InvalidQuery(AppError):
    code = "INVALID_QUERY"
    http_status = 400


class ProviderUnavailable(AppError):
    """Primary and fallback generation providers both failed."""
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503


class RateLimited(AppError):
    code = "RATE_LIMITED"
    retryable = True
    http_status = 429


class NoResults(AppError):
    """Every sub-need came back empty after relaxation.

    Not an error condition for individual empty groups — those are a normal
    response body (spec 7.2).
    """
    code = "NO_RESULTS"
    http_status = 200


class Internal(AppError):
    pass
