from app.core.exceptions import (
    AppError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    ProviderError,
)


def test_app_error_defaults():
    err = NotFoundError()
    assert err.code == "NOT_FOUND"
    assert err.status_code == 404
    assert err.message == "Not Found"


def test_app_error_custom_message():
    err = BadRequestError("bad input")
    assert err.message == "bad input"
    assert err.status_code == 400


def test_subclass_status_codes():
    assert ConflictError().status_code == 409
    assert ProviderError().status_code == 502
    assert AppError().status_code == 500
    assert AppError().code == "INTERNAL_ERROR"
