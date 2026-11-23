"""SeekAI New-API site (token only, no password fallback)."""

from src.core.secrets import SecretSpec
from src.platforms.newapi.base import NewApiPlatform, NewApiSite

TOKEN_SPEC = SecretSpec(
    logical_name="seekai_token",
    primary="CHECKIN_SEEKAI_TOKEN",
    legacy=("SEEKAI_TOKEN",),
    rolling=False,
)

SITE = NewApiSite(
    site_code="seekai",
    platform_name="SeekAI",
    base_url="https://seekai.cc",
    auth_mode="token",
    token_spec=TOKEN_SPEC,
    turnstile_env="SEEKAI_TURNSTILE_TOKEN",
)
PLATFORM = NewApiPlatform(SITE)


def seekai_platform() -> NewApiPlatform:
    return PLATFORM
