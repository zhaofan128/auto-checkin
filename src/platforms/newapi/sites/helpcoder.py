"""HelpCoder New-API site."""

from src.platforms.newapi.base import NewApiPlatform, NewApiSite

SITE = NewApiSite(
    site_code="helpcoder",
    platform_name="帮帮程序员",
    base_url="https://helpcoder.cc",
    auth_mode="password",
)
PLATFORM = NewApiPlatform(SITE)


def helpcoder_platform() -> NewApiPlatform:
    return PLATFORM
