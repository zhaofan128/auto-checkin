from src.core.redact import SensitiveStr, mask_account, redact_text, redact_turnstile


def test_mask_account():
    assert mask_account("zhangsan@example.com") == "zh***an"
    assert mask_account("ab") == "***"
    assert mask_account("abcdef") == "ab***ef"


def test_redact_text_patterns():
    text = redact_text(
        "token=nap_abcdefghijklmnopqrstuvwxyz password=hello "
        "Authorization: Bearer abc.def.ghi "
        "url=https://x.test/login?turnstile=abc123&x=1 "
        "mail user@example.com"
    )
    assert "nap_abcdefghijklmnopqrstuvwxyz" not in text
    assert "hello" not in text
    assert "abc.def.ghi" not in text
    assert "abc123" not in text
    assert "user@example.com" not in text
    assert "<REDACTED>" in text or "<EMAIL>" in text


def test_redact_turnstile_drops_token():
    payload = {
        "mode": "manual_token",
        "result": "manual_token",
        "token": "secret-turnstile-token",
        "attempts": 1,
        "manual_required": False,
    }
    redacted = redact_turnstile(payload)
    assert redacted is not None
    assert redacted["mode"] == "manual_token"
    assert redacted["token_present"] is True
    assert "token" not in redacted
    assert "secret-turnstile-token" not in str(redacted)


def test_sensitive_str_repr_and_str():
    value = SensitiveStr("top-secret")
    assert "top-secret" not in repr(value)
    assert "top-secret" not in str(value)
    assert value.reveal() == "top-secret"


def test_redact_text_keeps_normal_text():
    assert redact_text("签到成功，获得 100 积分") == "签到成功，获得 100 积分"
