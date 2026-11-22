"""Kemeng New-API site."""

from src.platforms.newapi.base import NewApiPlatform, NewApiSite

SITE = NewApiSite(
    site_code="kemeng",
    platform_name="可萌中转站",
    base_url="https://api456.me",
    auth_mode="password",
)
PLATFORM = NewApiPlatform(SITE)


def kemeng_platform() -> NewApiPlatform:
    return PLATFORM
