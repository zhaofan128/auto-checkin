"""New-API gateway platforms."""

from .base import NewApiAdapter, NewApiPlatform, NewApiSite
from .sites import (
    aiaiai_platform,
    benst_platform,
    dgb_platform,
    helpcoder_platform,
    kemeng_platform,
    seekai_platform,
)


def newapi_platforms():
    return [
        dgb_platform(),
        aiaiai_platform(),
        helpcoder_platform(),
        kemeng_platform(),
        seekai_platform(),
        benst_platform(),
    ]


__all__ = [
    "NewApiAdapter",
    "NewApiPlatform",
    "NewApiSite",
    "aiaiai_platform",
    "benst_platform",
    "dgb_platform",
    "helpcoder_platform",
    "kemeng_platform",
    "newapi_platforms",
    "seekai_platform",
]
