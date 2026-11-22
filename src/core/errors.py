"""Error types used by the unified check-in core."""

from __future__ import annotations


class CheckinError(Exception):
    error_type = "unknown_error"


class SecretMissing(CheckinError):
    error_type = "secret_missing"


class SecretWritebackUnavailable(CheckinError):
    error_type = "secret_writeback_unavailable"


class SecretWritebackFailed(CheckinError):
    error_type = "secret_writeback_failed"


class RefreshRequired(CheckinError):
    error_type = "refresh_required"


class RefreshFailed(CheckinError):
    error_type = "refresh_failed"


class ApiError(CheckinError):
    error_type = "api_error"


class StateConflict(CheckinError):
    error_type = "state_conflict"


class StateCorrupt(CheckinError):
    error_type = "state_corrupt"


class LockTimeout(CheckinError):
    error_type = "lock_timeout"


class TurnstileTimeout(CheckinError):
    error_type = "turnstile_timeout"


class BrowserLaunchFailed(CheckinError):
    error_type = "browser_launch_failed"


class HttpError(CheckinError):
    error_type = "http_error"

    def __init__(self, message: str, *, status: int | None = None, body: bytes | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class TransientError(CheckinError):
    error_type = "transient_error"
