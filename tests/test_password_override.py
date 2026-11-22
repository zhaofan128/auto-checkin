from src.core.secrets import SecretResolver


def test_global_default_applies_when_no_override():
    resolver = SecretResolver({"CHECKIN_USERNAME": "global", "CHECKIN_PASSWORD": "gpw"})
    creds = resolver.resolve_password("dgb")
    assert creds is not None
    assert creds.username == "global"
    assert creds.password == "gpw"
    assert creds.source == "global"


def test_site_override_applies():
    resolver = SecretResolver(
        {
            "CHECKIN_USERNAME": "global",
            "CHECKIN_PASSWORD": "gpw",
            "CHECKIN_USERNAME_AIAIAI": "site-user",
            "CHECKIN_PASSWORD_AIAIAI": "site-pw",
        }
    )
    creds = resolver.resolve_password("aiaiai")
    assert creds is not None
    assert creds.username == "site-user"
    assert creds.password == "site-pw"
    assert creds.source == "site_override"


def test_site_without_override_does_not_leak_other_site_credentials():
    resolver = SecretResolver(
        {
            "CHECKIN_USERNAME": "global",
            "CHECKIN_PASSWORD": "gpw",
            "CHECKIN_USERNAME_DGB": "dgb-user",
            "CHECKIN_PASSWORD_DGB": "dgb-pw",
        }
    )
    dgb = resolver.resolve_password("dgb")
    helpcoder = resolver.resolve_password("helpcoder")
    assert dgb is not None and helpcoder is not None
    assert dgb.username == "dgb-user"
    assert helpcoder.username == "global"
    assert helpcoder.password == "gpw"


def test_missing_global_returns_none():
    resolver = SecretResolver({})
    assert resolver.resolve_password("dgb") is None


def test_partial_override_falls_back_per_field():
    resolver = SecretResolver(
        {
            "CHECKIN_USERNAME": "global",
            "CHECKIN_PASSWORD": "gpw",
            "CHECKIN_USERNAME_KEMENG": "kemeng-user",
        }
    )
    creds = resolver.resolve_password("kemeng")
    assert creds is not None
    assert creds.username == "kemeng-user"
    assert creds.password == "gpw"


def test_password_credentials_repr_hides_password():
    resolver = SecretResolver({"CHECKIN_USERNAME": "u", "CHECKIN_PASSWORD": "secret-pw"})
    creds = resolver.resolve_password("dgb")
    assert "secret-pw" not in repr(creds)
