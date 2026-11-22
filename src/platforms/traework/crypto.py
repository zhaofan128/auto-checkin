"""TraeWork CN device proof and token exchange.

This is a direct port of the proven stdlib implementation. The custom P-256
signing path is intentionally kept as-is; do not replace it with a library
without golden-vector tests.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from src.core.http import HttpClient
from src.platforms.util import as_dict, first_number, response_json

UG_HOST = "https://api.trae.cn"
OAUTH_HOST = "https://api.trae.com.cn"
EP_EXCHANGE_PROOF = UG_HOST + "/trae/api/v3/oauth/ExchangeToken"
EP_EXCHANGE_LEGACY = OAUTH_HOST + "/cloudide/api/v3/trae/oauth/ExchangeToken"
PROOF_PATH = "/trae/api/v3/oauth/ExchangeToken"
CLIENT_ID_SOLO = "en1oxy7wnw8j9n"
CLIENT_ID_IDE = "ono9krqynydwx5"
IDE_VERSION = "1.107.1"
APP_ID = "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"
UA = "Trae/%s" % IDE_VERSION
TIMEOUT = 30

P256_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
P256_A = P256_P - 3
P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
P256_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
P256_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5


@dataclass(frozen=True)
class ExchangeResult:
    token: str | None
    refresh_token: str | None
    note: str


def _der_tlv(buf: bytes, i: int):
    tag = buf[i]
    i += 1
    ln = buf[i]
    i += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], "big")
        i += n
    return tag, buf[i:i + ln], i + ln


def _pem_der(pem: str) -> bytes:
    body = "".join(line.strip() for line in pem.splitlines() if "---" not in line)
    return base64.b64decode(body)


def ec_private_scalar(pem: str) -> int:
    der = _pem_der(pem)
    try:
        _, body, _ = _der_tlv(der, 0)
        i = 0
        _, _, i = _der_tlv(body, i)
        _, _, i = _der_tlv(body, i)
        _, octs, _ = _der_tlv(body, i)
        _, inner, _ = _der_tlv(octs, 0)
        j = 0
        _, _, j = _der_tlv(inner, j)
        _, d, _ = _der_tlv(inner, j)
        return int.from_bytes(d, "big")
    except Exception:
        _, body, _ = _der_tlv(der, 0)
        i = 0
        _, _, i = _der_tlv(body, i)
        _, d, _ = _der_tlv(body, i)
        return int.from_bytes(d, "big")


def _ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P256_P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + P256_A) * pow(2 * y1, -1, P256_P) % P256_P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P256_P) % P256_P
    x3 = (lam * lam - x1 - x2) % P256_P
    return x3, (lam * (x1 - x3) - y1) % P256_P


def _ec_mul(k: int, pt):
    result = None
    while k:
        if k & 1:
            result = _ec_add(result, pt)
        pt = _ec_add(pt, pt)
        k >>= 1
    return result


def _der_sig(r: int, s: int) -> bytes:
    def enc(value: int) -> bytes:
        buf = value.to_bytes(32, "big").lstrip(b"\x00") or b"\x00"
        if buf[0] & 0x80:
            buf = b"\x00" + buf
        return b"\x02" + bytes([len(buf)]) + buf

    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body


def ec_sign(pem: str, data: bytes) -> str:
    private = ec_private_scalar(pem)
    digest = int.from_bytes(hashlib.sha256(data).digest(), "big")
    while True:
        k = int.from_bytes(os.urandom(32), "big") % (P256_N - 1) + 1
        x1, _ = _ec_mul(k, (P256_GX, P256_GY))
        r = x1 % P256_N
        if r == 0:
            continue
        s = (pow(k, -1, P256_N) * (digest + r * private)) % P256_N
        if s == 0:
            continue
        if s > P256_N // 2:
            s = P256_N - s
        return base64.b64encode(_der_sig(r, s)).decode("ascii")


def device_proof(creds: Mapping[str, Any], client_id: str, platform_code: str) -> tuple[dict, dict]:
    timestamp = int(time.time())
    nonce = os.urandom(16).hex()
    canonical = "\n".join(
        [
            "POST",
            PROOF_PATH,
            client_id,
            str(creds.get("refresh_token") or ""),
            str(timestamp),
            nonce,
        ]
    )
    proof = {
        "Timestamp": timestamp,
        "Nonce": nonce,
        "Signature": ec_sign(str(creds.get("device_key_pem") or ""), canonical.encode("utf-8")),
    }
    info = {
        "DeviceID": creds.get("device_id", ""),
        "MachineID": creds.get("machine_id", ""),
        "PlatformCode": platform_code,
        "DeviceType": "PC",
        "DeviceName": "WorkBuddy-AutoCheckin",
        "DeviceModel": "",
        "ClientVersion": IDE_VERSION,
        "DevicePublicKey": creds.get("device_pub_pem", ""),
        "DeviceBrand": "",
        "DeviceCPU": "",
        "OSInfo": "Linux",
        "OSVersion": "",
    }
    return proof, info


def exchange_token(creds: Mapping[str, Any], http: HttpClient, *, timeout_s: int = TIMEOUT) -> ExchangeResult:
    if not (creds.get("refresh_token") and creds.get("device_id") and creds.get("device_key_pem")):
        return ExchangeResult(None, None, "TRAE_CREDS 不完整")

    last = ("", "")
    for client_id, platform_code in (
        (CLIENT_ID_IDE, "IDE_PC"),
        (CLIENT_ID_SOLO, "IDE_PC"),
        (CLIENT_ID_SOLO, "SOLO_PC"),
    ):
        try:
            proof, info = device_proof(creds, client_id, platform_code)
        except Exception as exc:  # noqa: BLE001 - signing failure is a typed result
            return ExchangeResult(None, None, f"设备签名失败: {exc}")
        body = json.dumps(
            {
                "ClientID": client_id,
                "ClientSecret": "",
                "RefreshToken": creds.get("refresh_token", ""),
                "DeviceInfo": info,
                "DeviceProof": proof,
                "IDEVersion": IDE_VERSION,
            }
        ).encode("utf-8")
        try:
            response = http.request(
                "POST",
                EP_EXCHANGE_PROOF,
                headers={"Content-Type": "application/json", "x-cloudide-token": ""},
                json_body=json.loads(body.decode("utf-8")),
                timeout_s=timeout_s,
                proxy="",
            )
        except Exception as exc:  # noqa: BLE001
            last = ("-1", str(exc))
            break
        payload = response_json(response)
        result = as_dict(payload.get("Result"))
        error_code = str(as_dict(as_dict(payload.get("ResponseMetadata")).get("Error")).get("Code") or "")
        if result.get("Token"):
            return ExchangeResult(
                str(result["Token"]),
                str(result.get("RefreshToken") or "") or None,
                f"ok:{client_id}/{platform_code}",
            )
        last = (str(response.status), json.dumps(payload, ensure_ascii=False)[:200])
        if error_code not in ("10101", "20403"):
            break

    try:
        response = http.request(
            "POST",
            EP_EXCHANGE_LEGACY,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": UA,
            },
            json_body={
                "ClientID": CLIENT_ID_SOLO,
                "RefreshToken": creds.get("refresh_token", ""),
                "ClientSecret": "-",
                "UserID": "",
            },
            timeout_s=timeout_s,
            proxy="",
        )
        payload = response_json(response)
        result = as_dict(payload.get("Result"))
        if result.get("Token"):
            return ExchangeResult(str(result["Token"]), None, "ok:legacy")
    except Exception as exc:  # noqa: BLE001
        return ExchangeResult(None, None, f"续期失败 http={last[0]} {exc}")

    return ExchangeResult(None, None, f"续期失败 http={last[0]} {last[1][:160]}")


def checkin_headers(token: str, creds: Mapping[str, Any]) -> dict[str, str]:
    return {
        "Authorization": "Cloud-IDE-JWT %s" % token,
        "X-Cloudide-Token": token,
        "x-uid": str(creds.get("uid") or ""),
        "x-app-id": APP_ID,
        "x-device-id": str(creds.get("device_id") or ""),
        "x-machine-id": str(creds.get("machine_id") or ""),
        "x-request-id": str(uuid.uuid4()),
        "x-ide-version": IDE_VERSION,
        "x-ide-version-code": IDE_VERSION.replace(".", ""),
        "x-device-type": "windows",
        "x-os-version": "Windows",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }


def extract_credits(data: Mapping[str, Any]) -> tuple[int | float | None, int | float | None]:
    """Return (gained, current) from Trae claim data without inventing values."""

    gained = first_number(
        data.get("credits_earned_today"),
        data.get("grant_credits"),
        data.get("credits"),
    )
    current = first_number(data.get("total_credits"))
    return gained, current
