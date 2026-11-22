"""AIAIAI New-API site."""

from src.platforms.newapi.base import NewApiPlatform, NewApiSite

SITE = NewApiSite(
    site_code="aiaiai",
    platform_name="AIAIAI 工具箱",
    base_url="https://api.aiaiai001.com",
    auth_mode="password",
)
PLATFORM = NewApiPlatform(SITE)


def aiaiai_platform() -> NewApiPlatform:
    return PLATFORM
