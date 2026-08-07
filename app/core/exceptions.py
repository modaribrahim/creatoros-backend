class AppError(Exception):
    """Base class for all API errors.

    Every error exposed to the frontend carries a stable `code` (the
    machine-readable contract) and a human `message`. HTTP status is a
    consequence of the code, never a separate decision.
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)

    @property
    def default_message(self) -> str:
        return self.code.replace("_", " ").title()


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class ProviderError(AppError):
    status_code = 502
    code = "PROVIDER_ERROR"


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
