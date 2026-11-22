"""BENST New-API site (token only, 02:00 quota window)."""

from src.core.secrets import SecretSpec
from src.platforms.newapi.base import NewApiPlatform, NewApiSite

TOKEN_SPEC = SecretSpec(
    logical_name="benst_token",
    primary="CHECKIN_BENST_TOKEN",
    legacy=("BENST_TOKEN",),
    rolling=False,
)

SITE = NewApiSite(
    site_code="benst",
    platform_name="神秘小站 BENST",
    base_url="http://newapi.benst.asia",
    auth_mode="token",
    token_spec=TOKEN_SPEC,
    schedule_profiles=frozenset({"quota", "morning", "midmorning", "afternoon", "manual"}),
    quota_window=True,
)
PLATFORM = NewApiPlatform(SITE)


def benst_platform() -> NewApiPlatform:
    return PLATFORM
