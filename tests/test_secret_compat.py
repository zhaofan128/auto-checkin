from src.core.secrets import SecretResolver, SecretSpec


WB_SPEC = SecretSpec(
    logical_name="workbuddy_rt",
    primary="CHECKIN_WORKBUDDY_RT",
    legacy=("WB_RT",),
    rolling=True,
)


class FakeGitHub:
    def __init__(self, writable: bool = True, versions: dict[str, str] | None = None) -> None:
        self.writable = writable
        self.writes: list[tuple[str, str]] = []
        self.versions = dict(versions or {})

    def can_write(self) -> bool:
        return self.writable

    def set_secret(self, name: str, value: str) -> str | None:
        self.writes.append((name, value))
        self.versions[name] = "2026-11-22T00:00:00Z"
        return self.versions[name]

    def get_secret_updated_at(self, name: str) -> str | None:
        return self.versions.get(name)


def test_prefers_new_key():
    resolver = SecretResolver({"CHECKIN_WORKBUDDY_RT": "new", "WB_RT": "old"})
    resolved = resolver.resolve(WB_SPEC)
    assert resolved is not None
    assert resolved.source_key == "CHECKIN_WORKBUDDY_RT"
    assert resolved.value == "new"


def test_falls_back_to_legacy_key():
    resolver = SecretResolver({"WB_RT": "old"})
    resolved = resolver.resolve(WB_SPEC)
    assert resolved is not None
    assert resolved.source_key == "WB_RT"


def test_missing_returns_none():
    assert SecretResolver({}).resolve(WB_SPEC) is None


def test_write_back_keeps_legacy_key_fresh():
    github = FakeGitHub()
    resolver = SecretResolver({"CHECKIN_WORKBUDDY_RT": "new"}, github=github)
    result = resolver.write_back(WB_SPEC, "rotated", "CHECKIN_WORKBUDDY_RT")
    assert result.ok is True
    written = {name for name, _ in github.writes}
    assert "CHECKIN_WORKBUDDY_RT" in written
    assert "WB_RT" in written


def test_write_back_does_not_create_new_alias_when_only_legacy_configured():
    github = FakeGitHub()
    resolver = SecretResolver({"WB_RT": "old"}, github=github)
    result = resolver.write_back(WB_SPEC, "rotated", "WB_RT")
    assert result.ok is True
    written = [name for name, _ in github.writes]
    assert "WB_RT" in written
    assert "CHECKIN_WORKBUDDY_RT" not in written


def test_write_back_reports_unavailable_without_pat():
    resolver = SecretResolver({"WB_RT": "old"}, github=None)
    result = resolver.write_back(WB_SPEC, "rotated", "WB_RT")
    assert result.ok is False
    assert result.error == "secret_writeback_unavailable"


def test_secret_value_repr_hides_value():
    resolver = SecretResolver({"WB_RT": "super-secret-value"})
    resolved = resolver.resolve(WB_SPEC)
    assert "super-secret-value" not in repr(resolved)
