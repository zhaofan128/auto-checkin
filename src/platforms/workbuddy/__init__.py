"""WorkBuddy platform package."""

from .adapter import (
    WB_SECRET,
    WORKBUDDY_ACCOUNT,
    WORKBUDDY_SPEC,
    WorkBuddyAdapter,
    WorkBuddyPlatform,
    workbuddy_platform,
)

__all__ = [
    "WB_SECRET",
    "WORKBUDDY_ACCOUNT",
    "WORKBUDDY_SPEC",
    "WorkBuddyAdapter",
    "WorkBuddyPlatform",
    "workbuddy_platform",
]
