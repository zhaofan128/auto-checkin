"""Turnstile observation and solving path.

KK defaults to manual_token because GitHub Actions data-center IPs are in
Cloudflare's elevated-risk ranges. Browser evaluation is only a fallback when
KK_TURNSTILE_TOKEN is not configured.

Priority:
  manual_token > browser_fallback > turnstile_timeout

The token never appears in logs or repr.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from src.core.redact import SensitiveStr


class TurnstileMode(str, Enum):
    MANUAL_TOKEN = "manual_token"
    BROWSER_FALLBACK = "browser_fallback"


def manual_token_from_env(env: Mapping[str, str]) -> str | None:
    """The single manual channel for a Turnstile token."""

    return (env.get("KK_TURNSTILE_TOKEN") or "").strip() or None


def select_turnstile_mode(manual_token: str | None) -> TurnstileMode:
    return TurnstileMode.MANUAL_TOKEN if (manual_token or "").strip() else TurnstileMode.BROWSER_FALLBACK


@dataclass(frozen=True)
class TurnstileStrategy:
    mode: TurnstileMode
    manual_token: SensitiveStr | None = None


def resolve_turnstile_strategy(env: Mapping[str, str]) -> TurnstileStrategy:
    """Default to manual_token; use browser_fallback only when it is absent."""

    token = manual_token_from_env(env)
    if token:
        return TurnstileStrategy(TurnstileMode.MANUAL_TOKEN, SensitiveStr(token))
    return TurnstileStrategy(TurnstileMode.BROWSER_FALLBACK, None)


@dataclass(frozen=True)
class TurnstileOutcome:
    mode: TurnstileMode
    result: str
    token: SensitiveStr | None
    attempts: int
    clicks: int
    duration_ms: int
    manual_required: bool

    @classmethod
    def manual_token(cls, token: str) -> "TurnstileOutcome":
        return cls(
            mode=TurnstileMode.MANUAL_TOKEN,
            result="manual_token",
            token=SensitiveStr(token),
            attempts=1,
            clicks=0,
            duration_ms=0,
            manual_required=False,
        )

    def log_fields(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "result": self.result,
            "attempts": self.attempts,
            "clicks": self.clicks,
            "manual_required": self.manual_required,
            "duration_ms": self.duration_ms,
            "token_present": bool(self.token),
        }


_JS_DETECT = """
() => {
  const input = document.querySelector('input[name="cf-turnstile-response"]');
  if (input && input.value) return {state: 'solved', token: input.value};
  try {
    const value = window.turnstile && window.turnstile.getResponse && window.turnstile.getResponse();
    if (value) return {state: 'solved', token: value};
  } catch (error) {}
  const frame = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
  return {state: frame ? 'pending' : 'absent', token: ''};
}
"""


class TurnstileEvaluator:
    def __init__(self, *, poll_interval_ms: int = 2000, click_interval_ms: int = 15000) -> None:
        self.poll_interval_ms = poll_interval_ms
        self.click_interval_ms = click_interval_ms

    async def detect(self, page: Any) -> tuple[str, str | None]:
        data = await page.evaluate(_JS_DETECT)
        if not isinstance(data, dict):
            return "absent", None
        token = data.get("token") or None
        return str(data.get("state") or "absent"), token

    async def try_click(self, page: Any) -> bool:
        for frame in page.frames:
            url = getattr(frame, "url", "") or ""
            if "challenges.cloudflare.com" not in url:
                continue
            try:
                element = await frame.frame_element()
                box = await element.bounding_box()
            except Exception:
                continue
            if not box or box.get("width", 0) <= 50 or box.get("height", 0) <= 20:
                continue
            try:
                await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                return True
            except Exception:
                return False
        return False

    async def solve(self, page: Any, *, timeout_ms: int, max_clicks: int = 3) -> TurnstileOutcome:
        started = time.monotonic()
        deadline = started + max(0, timeout_ms) / 1000
        attempts = 0
        clicks = 0
        absent_polls = 0
        last_click = 0.0

        while time.monotonic() < deadline:
            attempts += 1
            state, token = await self.detect(page)
            if token:
                return TurnstileOutcome(
                    mode=TurnstileMode.BROWSER_FALLBACK,
                    result="solved",
                    token=SensitiveStr(token),
                    attempts=attempts,
                    clicks=clicks,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    manual_required=False,
                )

            if state == "absent":
                absent_polls += 1
                if absent_polls >= 3:
                    return TurnstileOutcome(
                        mode=TurnstileMode.BROWSER_FALLBACK,
                        result="not_present",
                        token=None,
                        attempts=attempts,
                        clicks=clicks,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        manual_required=False,
                    )
            else:
                absent_polls = 0

            if (
                state == "pending"
                and clicks < max_clicks
                and (time.monotonic() - last_click) >= self.click_interval_ms / 1000
            ):
                if await self.try_click(page):
                    clicks += 1
                    last_click = time.monotonic()

            await page.wait_for_timeout(self.poll_interval_ms)

        return TurnstileOutcome(
            mode=TurnstileMode.BROWSER_FALLBACK,
            result="timeout",
            token=None,
            attempts=attempts,
            clicks=clicks,
            duration_ms=int((time.monotonic() - started) * 1000),
            manual_required=True,
        )
