import json
from pathlib import Path

from src.core.http import HttpResponse
from src.core.logging import EventLogger
from src.core.models import AccountRef
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore
from src.platforms.base import AccountContext


def response(payload, status: int = 200, set_cookies=()) -> HttpResponse:
    return HttpResponse(
        status,
        {},
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        set_cookies=tuple(set_cookies),
    )


class FakeHttp:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    def request(self, method, url, *, headers=None, json_body=None, **kwargs):
        self.calls.append((method, url))
        return self.handler(method, url, json_body=json_body, headers=headers or {})


def make_context(
    tmp_path: Path,
    http,
    account: AccountRef,
    env: dict[str, str],
    *,
    dry_run: bool = False,
) -> AccountContext:
    return AccountContext(
        run_id="test-run",
        profile="manual",
        account=account,
        http=http,  # type: ignore[arg-type]
        secrets=SecretResolver(env),
        state=AccountStateStore(tmp_path / "state"),
        logger=EventLogger(tmp_path / "history", run_id="test-run"),
        dry_run=dry_run,
    )
