"""Playwright/Patchright browser fallback for Turnstile-protected check-ins.

The manual token is optional. When it is absent, this module opens the login
page, waits for the Turnstile response, and performs the check-in fetch inside
the browser context. The token itself is never returned or logged.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True)
class BrowserCheckinResult:
    ok: bool
    status: int
    payload: dict[str, Any]
    turnstile_result: str
    attempts: int
    clicks: int
    duration_ms: int
    screenshot: str | None = None
    error: str | None = None
    token_present: bool = False


def _load_sync_playwright():
    try:
        from patchright.sync_api import sync_playwright  # type: ignore

        return sync_playwright, "patchright"
    except Exception:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            return sync_playwright, "playwright"
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("playwright/patchright 未安装") from exc


def _token_from_page(page) -> str:
    return str(
        page.evaluate(
            """() => {
                const input = document.querySelector('input[name="cf-turnstile-response"]');
                if (input && input.value) return input.value;
                try {
                    return (window.turnstile && window.turnstile.getResponse && window.turnstile.getResponse()) || '';
                } catch (_) {
                    return '';
                }
            }"""
        )
        or ""
    )


def _click_challenge(page) -> bool:
    for frame in page.frames:
        if "challenges.cloudflare.com" not in frame.url:
            continue
        try:
            element = frame.frame_element()
            box = element.bounding_box()
            if box and box.get("width", 0) > 50 and box.get("height", 0) > 20:
                page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                return True
        except Exception:
            continue
    return False


def _launch(browser_type, *, headless: bool, channel: str | None, executable_path: str | None, proxy: str | None):
    options: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if executable_path:
        options["executable_path"] = executable_path
    if proxy:
        options["proxy"] = {"server": proxy}
    if channel:
        try:
            return browser_type.launch(channel=channel, **options)
        except Exception:
            pass
    return browser_type.launch(**options)


def browser_checkin(
    base_url: str,
    login_path: str,
    checkin_path: str,
    bearer_token: str,
    *,
    timeout_ms: int | None = None,
    max_attempts: int | None = None,
    headless: bool | None = None,
    channel: str | None = None,
    executable_path: str | None = None,
    proxy: str | None = None,
) -> BrowserCheckinResult:
    """Open login page, solve Turnstile, and POST the check-in inside the browser."""

    timeout_ms = max(15000, timeout_ms or int(os.environ.get("KK_TOKEN_TIMEOUT_MS", "90000")))
    max_attempts = max(1, max_attempts or int(os.environ.get("KK_MAX_ATTEMPTS", "3")))
    if headless is None:
        headless = os.environ.get("KK_HEADLESS", "1") != "0"
    channel = channel if channel is not None else os.environ.get("KK_CHANNEL")
    executable_path = executable_path or os.environ.get("PLAYWRIGHT_CHROME_PATH")
    proxy = proxy or os.environ.get("KK_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    started = time.monotonic()
    last_error: str | None = None
    last_screenshot: str | None = None

    try:
        sync_playwright, _engine = _load_sync_playwright()
    except RuntimeError as exc:
        return BrowserCheckinResult(
            ok=False,
            status=0,
            payload={},
            turnstile_result="browser_unavailable",
            attempts=0,
            clicks=0,
            duration_ms=0,
            error=str(exc),
        )

    with sync_playwright() as pw:
        for attempt in range(1, max_attempts + 1):
            browser = None
            clicks = 0
            try:
                browser = _launch(
                    pw.chromium,
                    headless=headless,
                    channel=channel,
                    executable_path=executable_path,
                    proxy=proxy,
                )
                context = browser.new_context(
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    viewport={"width": 1366, "height": 800},
                )
                page = context.new_page()
                page.goto(base_url + login_path, wait_until="domcontentloaded", timeout=60000)
                deadline = time.monotonic() + timeout_ms / 1000
                last_click = 0.0
                token = ""
                while time.monotonic() < deadline:
                    token = _token_from_page(page)
                    if token:
                        break
                    if clicks < 3 and time.monotonic() - last_click > 15:
                        if _click_challenge(page):
                            clicks += 1
                            last_click = time.monotonic()
                    page.wait_for_timeout(2000)
                if not token:
                    last_screenshot = f"/tmp/turnstile-timeout-{attempt}.png"
                    try:
                        page.screenshot(path=last_screenshot)
                    except Exception:
                        last_screenshot = None
                    last_error = "Turnstile 验证超时"
                    if attempt < max_attempts:
                        time.sleep(15 * attempt)
                        continue
                    return BrowserCheckinResult(
                        ok=False,
                        status=0,
                        payload={},
                        turnstile_result="timeout",
                        attempts=attempt,
                        clicks=clicks,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        screenshot=last_screenshot,
                        error=last_error,
                        token_present=False,
                    )

                checkin_url = base_url + checkin_path + "?turnstile=" + quote(token, safe="")
                result = page.evaluate(
                    """async ({url, auth}) => {
                        try {
                            const r = await fetch(url, {
                                method: 'POST',
                                headers: {
                                    'Authorization': 'Bearer ' + auth,
                                    'Content-Type': 'application/json'
                                },
                                body: '{}'
                            });
                            return {status: r.status, text: await r.text()};
                        } catch (err) {
                            return {error: String(err)};
                        }
                    }""",
                    {"url": checkin_url, "auth": bearer_token},
                )
                if not isinstance(result, dict):
                    result = {"error": "浏览器返回空结果"}
                if result.get("error"):
                    last_error = "浏览器内签到请求失败: " + str(result["error"])[:160]
                else:
                    status = int(result.get("status") or 0)
                    text = str(result.get("text") or "")
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        payload = {"raw": text[:300]}
                    return BrowserCheckinResult(
                        ok=200 <= status < 300,
                        status=status,
                        payload=payload if isinstance(payload, dict) else {"data": payload},
                        turnstile_result="solved",
                        attempts=attempt,
                        clicks=clicks,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        token_present=True,
                    )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:200]
            finally:
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
            if attempt < max_attempts:
                time.sleep(15 * attempt)

    return BrowserCheckinResult(
        ok=False,
        status=0,
        payload={},
        turnstile_result="browser_error",
        attempts=max_attempts,
        clicks=0,
        duration_ms=int((time.monotonic() - started) * 1000),
        screenshot=last_screenshot,
        error=last_error or "浏览器执行失败",
        token_present=False,
    )
