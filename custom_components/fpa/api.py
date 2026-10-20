"""Home Assistant boundary for the maintained Baby Brezza cloud client."""

from .vendor.pybabyfpa import (
    ApiError,
    AuthenticationError,
    CommandError,
    ConnectionError,
    FpaClient,
)

__all__ = [
    "ApiError",
    "AuthenticationError",
    "CommandError",
    "ConnectionError",
    "FpaClient",
]
