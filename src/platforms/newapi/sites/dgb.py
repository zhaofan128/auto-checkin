"""DGB New-API site."""

from src.platforms.newapi.base import NewApiPlatform, NewApiSite

SITE = NewApiSite(
    site_code="dgb",
    platform_name="DGB 公益站",
    base_url="https://freeapi.dgbmc.top",
    auth_mode="password",
)
PLATFORM = NewApiPlatform(SITE)


def dgb_platform() -> NewApiPlatform:
    return PLATFORM
