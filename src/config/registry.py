"""Platform/account registry.

Concrete platform adapters are intentionally not implemented in this step.
"""

from __future__ import annotations

from typing import Iterable

from src.platforms.base import AccountSpec, PlatformAdapter
from src.platforms.kk import kk_platform
from src.platforms.lobsterai import lobsterai_platform
from src.platforms.minimax import minimax_platform
from src.platforms.newapi import newapi_platforms
from src.platforms.qoder import qoder_platform
from src.platforms.traework import traework_platform
from src.platforms.workbuddy import workbuddy_platform


class PlatformRegistry:
    def __init__(self, adapters: Iterable[PlatformAdapter] = ()) -> None:
        self._specs: dict[str, AccountSpec] = {}
        self._adapters: dict[str, PlatformAdapter] = {}
        self._order: list[str] = []
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: PlatformAdapter) -> None:
        for spec in adapter.accounts:
            if spec.account_key in self._specs:
                raise ValueError(f"重复注册账户: {spec.account_key}")
            self._specs[spec.account_key] = spec
            self._adapters[spec.account_key] = adapter
            self._order.append(spec.account_key)

    def all_specs(self) -> tuple[AccountSpec, ...]:
        return tuple(self._specs[key] for key in self._order)

    def get_spec(self, account_key: str) -> AccountSpec:
        return self._specs[account_key]

    def adapter_for(self, account_key: str) -> PlatformAdapter:
        return self._adapters[account_key]

    def select(self, profile: str, platforms: set[str] | None = None) -> list[AccountSpec]:
        selected: list[AccountSpec] = []
        for key in self._order:
            spec = self._specs[key]
            if platforms and spec.platform not in platforms and spec.account_key not in platforms:
                continue
            if profile != "manual" and profile not in spec.schedule_profiles:
                continue
            selected.append(spec)
        return selected


def build_registry(adapters: Iterable[PlatformAdapter]) -> PlatformRegistry:
    return PlatformRegistry(adapters)


def build_default_registry() -> PlatformRegistry:
    """All 12 adapters / 13 account targets."""

    adapters = [
        workbuddy_platform(),
        traework_platform(),
        qoder_platform(),
        minimax_platform(),
        lobsterai_platform(),
        kk_platform(),
        *newapi_platforms(),
    ]
    return PlatformRegistry(adapters)
