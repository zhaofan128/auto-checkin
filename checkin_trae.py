#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TraeWork CN 每日签到。凭据从环境变量 TRAE_CREDS（JSON 字符串）读取：
{"refresh_token": "...", "device_id": "...", "machine_id": "...", "uid": "...",
 "device_key_pem": "...", "device_pub_pem": "..."}
"""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

CREDS = {}
_raw = os.environ.get("TRAE_CREDS", "").strip()
if _raw:
    try:
        CREDS = json.loads(_raw)
    except Exception:
        CREDS = {}

REFRESH_TOKEN = CREDS.get("refresh_token", "")
DEVICE_ID = CREDS.get("device_id", "")
MACHINE_ID = CREDS.get("machine_id", "")
UID = CREDS.get("uid", "")
DEVICE_KEY_PEM = CREDS.get("device_key_pem", "")
DEVICE_PUB_PEM = CREDS.get("device_pub_pem", "")

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

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_G = {"rotated": False}  # 标记本次是否拿到了新的 refreshToken


def _post(url, headers, body="{}"):
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:
            return e.code, ""
    except Exception as e:
        return -1, str(e)


P256_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
P256_A = P256_P - 3
P256_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
P256_GX = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296
P256_GY = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5


def _der_tlv(buf, i):
    tag = buf[i]
    i += 1
    ln = buf[i]
    i += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], "big")
        i += n
    return tag, buf[i:i + ln], i + ln


def _pem_der(pem):
    body = "".join(l.strip() for l in pem.splitlines() if "---" not in l)
    return base64.b64decode(body)


def ec_private_scalar(pem):
    der = _pem_der(pem)
    try:
        _, body, _ = _der_tlv(der, 0)
        i = 0
        _, _, i = _der_tlv(body, i)
        _, _, i = _der_tlv(body, i)
        _, octs, i = _der_tlv(body, i)
        _, inner, _ = _der_tlv(octs, 0)
        j = 0
        _, _, j = _der_tlv(inner, j)
        _, d, j = _der_tlv(inner, j)
        return int.from_bytes(d, "big")
    except Exception:
        _, body, _ = _der_tlv(der, 0)
        i = 0
        _, _, i = _der_tlv(body, i)
        _, d, i = _der_tlv(body, i)
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


def _ec_mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = _ec_add(r, pt)
        pt = _ec_add(pt, pt)
        k >>= 1
    return r


def _der_sig(r, s):
    def enc(x):
        b = x.to_bytes(32, "big").lstrip(b"\x00") or b"\x00"
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b

    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body


def ec_sign(pem, data):
    d = ec_private_scalar(pem)
    z = int.from_bytes(hashlib.sha256(data).digest(), "big")
    while True:
        k = int.from_bytes(os.urandom(32), "big") % (P256_N - 1) + 1
        x1, _ = _ec_mul(k, (P256_GX, P256_GY))
        r = x1 % P256_N
        if r == 0:
            continue
        s = (pow(k, -1, P256_N) * (z + r * d)) % P256_N
        if s == 0:
            continue
        if s > P256_N // 2:
            s = P256_N - s
        return base64.b64encode(_der_sig(r, s)).decode("ascii")


def device_proof(client_id, platform_code):
    ts = int(time.time())
    nonce = os.urandom(16).hex()
    canonical = "\n".join(["POST", PROOF_PATH, client_id, REFRESH_TOKEN, str(ts), nonce])
    proof = {"Timestamp": ts, "Nonce": nonce,
             "Signature": ec_sign(DEVICE_KEY_PEM, canonical.encode("utf-8"))}
    info = {"DeviceID": DEVICE_ID, "MachineID": MACHINE_ID,
            "PlatformCode": platform_code, "DeviceType": "PC",
            "DeviceName": "WorkBuddy-AutoCheckin", "DeviceModel": "",
            "ClientVersion": IDE_VERSION, "DevicePublicKey": DEVICE_PUB_PEM,
            "DeviceBrand": "", "DeviceCPU": "",
            "OSInfo": "Linux", "OSVersion": ""}
    return proof, info


def refresh():
    combos = [(CLIENT_ID_IDE, "IDE_PC"), (CLIENT_ID_SOLO, "IDE_PC"), (CLIENT_ID_SOLO, "SOLO_PC")]
    last = ("", "")
    for cid, pcode in combos:
        try:
            proof, info = device_proof(cid, pcode)
        except Exception as e:
            return None, "设备签名失败: %s" % e
        body = json.dumps({"ClientID": cid, "ClientSecret": "", "RefreshToken": REFRESH_TOKEN,
                           "DeviceInfo": info, "DeviceProof": proof, "IDEVersion": IDE_VERSION})
        st, text = _post(EP_EXCHANGE_PROOF, {"Content-Type": "application/json",
                                             "x-cloudide-token": ""}, body)
        try:
            res = json.loads(text).get("Result") or {}
            code = ((json.loads(text).get("ResponseMetadata") or {}).get("Error") or {}).get("Code")
        except Exception:
            res, code = {}, None
        if res.get("Token"):
            # 滚动续期：把新的 refreshToken 写回凭据文件，由 workflow 更新 Secret
            new_rt = res.get("RefreshToken") or ""
            if new_rt:
                try:
                    new_creds = dict(CREDS)
                    new_creds["refresh_token"] = new_rt
                    with open(os.environ.get("TRAE_NEW_CREDS_FILE", "trae_new_creds.json"),
                              "w", encoding="utf-8") as f:
                        json.dump(new_creds, f, ensure_ascii=False)
                    _G["rotated"] = True
                except Exception:
                    pass
            return res["Token"], "ok:%s/%s" % (cid, pcode)
        last = (str(st), text[:200])
        if str(code) not in ("10101", "20403"):
            break
    body = json.dumps({"ClientID": CLIENT_ID_SOLO, "RefreshToken": REFRESH_TOKEN,
                       "ClientSecret": "-", "UserID": ""})
    st, text = _post(EP_EXCHANGE_LEGACY, {"Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA}, body)
    try:
        res = json.loads(text).get("Result") or {}
    except Exception:
        res = {}
    if res.get("Token"):
        return res["Token"], "ok:legacy"
    return None, "续期失败 http=%s %s" % (last[0], last[1][:160])


def checkin_headers(token):
    return {
        "Authorization": "Cloud-IDE-JWT %s" % token,
        "X-Cloudide-Token": token,
        "x-uid": UID, "x-app-id": APP_ID,
        "x-device-id": DEVICE_ID, "x-machine-id": MACHINE_ID,
        "x-request-id": str(uuid.uuid4()),
        "x-ide-version": IDE_VERSION,
        "x-ide-version-code": IDE_VERSION.replace(".", ""),
        "x-device-type": "windows", "x-os-version": "Windows",
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA,
    }


def mask(t):
    return (t[:8] + "..." + t[-6:]) if len(t) > 18 else "***"


def main():
    if not (REFRESH_TOKEN and DEVICE_ID and DEVICE_KEY_PEM):
        print(json.dumps({"ok": False, "stage": "config", "msg": "TRAE_CREDS 未设置或不完整"},
                         ensure_ascii=False))
        return 2
    token, note = refresh()
    if not token:
        print(json.dumps({"ok": False, "stage": "refresh", "msg": note}, ensure_ascii=False))
        return 2
    out = {"ok": True, "refresh": note, "token": mask(token), "rotated": _G["rotated"]}
    h = checkin_headers(token)
    st, text = _post(UG_HOST + "/trae/api/v2/ug/checkin_credits/status", h, '{"req_source":1}')
    try:
        s = json.loads(text)
    except Exception:
        s = {}
    data = s.get("data") or s
    out["checked_in"] = data.get("checked_in")
    out["credits"] = data.get("credits")
    if s.get("code") not in (0, None):
        out["ok"] = False
        out["msg"] = "状态查询异常 code=%s %s" % (s.get("code"), (s.get("message") or "")[:120])
        print(json.dumps(out, ensure_ascii=False))
        return 1
    if data.get("checked_in"):
        out["checkin"] = "already"
    else:
        cst, ctext = _post(UG_HOST + "/trae/api/v2/ug/checkin_credits/claim", h, '{"req_source":1}')
        try:
            c = json.loads(ctext)
        except Exception:
            c = {}
        cdata = c.get("data") or c
        out["claim_code"] = c.get("code")
        if c.get("code") in (0, None) and cst < 400:
            out["checkin"] = "claimed"
            out["claim_credits"] = cdata.get("credits") or cdata.get("grant_credits")
        else:
            out["ok"] = False
            out["checkin"] = "failed"
            out["msg"] = "领取失败 code=%s %s" % (c.get("code"), (c.get("message") or "")[:120])
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
