"""Minimal HTTP client shared by platform adapters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import HttpError


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    set_cookies: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)


class HttpClient:
    def __init__(self, *, user_agent: str = "AutoCheckin/2.0", timeout_s: float = 25.0) -> None:
        self.user_agent = user_agent
        self.timeout_s = timeout_s

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any = None,
        timeout_s: float | None = None,
        proxy: str | None = None,
    ) -> HttpResponse:
        request_headers: dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers=request_headers,
        )
        if proxy == "":
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        elif proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
        else:
            opener = urllib.request.build_opener()

        try:
            with opener.open(request, timeout=timeout_s or self.timeout_s) as response:
                return HttpResponse(
                    response.status,
                    dict(response.headers),
                    response.read(),
                    set_cookies=tuple(response.headers.get_all("Set-Cookie") or ()),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                exc.code,
                dict(exc.headers),
                exc.read(),
                set_cookies=tuple(exc.headers.get_all("Set-Cookie") or ()),
            )
        except Exception as exc:  # noqa: BLE001 - network failures become typed errors
            raise HttpError(f"网络请求失败: {exc}") from exc
