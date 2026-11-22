import asyncio

from src.browser.turnstile import (
    TurnstileEvaluator,
    TurnstileMode,
    TurnstileOutcome,
    manual_token_from_env,
    resolve_turnstile_strategy,
    select_turnstile_mode,
)


class FakeMouse:
    def __init__(self) -> None:
        self.clicks = 0

    async def click(self, x: float, y: float) -> None:
        self.clicks += 1


class FakePage:
    def __init__(self, states: list[dict]) -> None:
        self.states = states
        self.frames: list = []
        self.mouse = FakeMouse()

    async def evaluate(self, script: str) -> dict:
        if self.states:
            return self.states.pop(0)
        return {"state": "pending", "token": ""}

    async def wait_for_timeout(self, ms: int) -> None:
        return None


def test_manual_token_has_priority():
    assert select_turnstile_mode("manual-token") is TurnstileMode.MANUAL_TOKEN
    assert select_turnstile_mode(None) is TurnstileMode.BROWSER_FALLBACK
    assert select_turnstile_mode("   ") is TurnstileMode.BROWSER_FALLBACK
    assert manual_token_from_env({"KK_TURNSTILE_TOKEN": "manual-token"}) == "manual-token"
    assert manual_token_from_env({"KK_TURNSTILE_TOKEN": "  "}) is None
    assert manual_token_from_env({}) is None


def test_turnstile_strategy_defaults_to_manual_when_configured():
    manual = resolve_turnstile_strategy({"KK_TURNSTILE_TOKEN": "manual-token"})
    assert manual.mode is TurnstileMode.MANUAL_TOKEN
    assert manual.manual_token is not None
    assert manual.manual_token.reveal() == "manual-token"
    assert "manual-token" not in repr(manual)

    fallback = resolve_turnstile_strategy({})
    assert fallback.mode is TurnstileMode.BROWSER_FALLBACK
    assert fallback.manual_token is None


def test_manual_token_log_fields_never_expose_token():
    outcome = TurnstileOutcome.manual_token("secret-turnstile-value")
    fields = outcome.log_fields()
    assert fields["mode"] == "manual_token"
    assert fields["result"] == "manual_token"
    assert fields["token_present"] is True
    assert "secret-turnstile-value" not in str(fields)
    assert "secret-turnstile-value" not in repr(outcome)


def test_browser_solved_outcome():
    page = FakePage([{"state": "solved", "token": "browser-token-value"}])
    evaluator = TurnstileEvaluator(poll_interval_ms=1, click_interval_ms=1)
    outcome = asyncio.run(evaluator.solve(page, timeout_ms=100))
    assert outcome.result == "solved"
    assert outcome.mode is TurnstileMode.BROWSER_FALLBACK
    assert outcome.token is not None
    assert outcome.token.reveal() == "browser-token-value"
    assert "browser-token-value" not in str(outcome.log_fields())
    assert outcome.log_fields()["mode"] == "browser_fallback"


def test_browser_timeout_requires_manual_intervention():
    page = FakePage([{"state": "pending", "token": ""} for _ in range(20)])
    evaluator = TurnstileEvaluator(poll_interval_ms=1, click_interval_ms=1)
    outcome = asyncio.run(evaluator.solve(page, timeout_ms=20, max_clicks=0))
    assert outcome.result == "timeout"
    assert outcome.mode is TurnstileMode.BROWSER_FALLBACK
    assert outcome.manual_required is True
    assert outcome.token is None


def test_absent_turnstile_is_detected_quickly():
    page = FakePage([{"state": "absent", "token": ""} for _ in range(3)])
    evaluator = TurnstileEvaluator(poll_interval_ms=1)
    outcome = asyncio.run(evaluator.solve(page, timeout_ms=100))
    assert outcome.result == "not_present"
    assert outcome.mode is TurnstileMode.BROWSER_FALLBACK
    assert outcome.manual_required is False
