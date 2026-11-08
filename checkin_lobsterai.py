#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LobsterAI（有道龙虾）每日签到。协议四步（已实测跑通）：

0) GET  {clientVersionApi}                                  -> data.value.version
1) GET  /api/client-activities/slot?placement=desktop_sidebar&containerApiVersion=2&platform=win32&clientVersion={v}
2) GET  /api/client-activities/{activityCode}/context?configRevision={rev}
3) POST /api/client-activities/{activityCode}/actions/check_in
       body: {configRevision, idempotencyKey: uuid4, payload: {}}

凭据从环境变量 LOBSTER_CREDS 读取（JSON：access_token/refresh_token/uid/uuid/first_keyfrom/latest_keyfrom）。
续期：POST /api/auth/refresh（不带 Authorization），body = keyfrom + refreshToken。
⚠️ 有道会封禁「经第三方代理/插件转接」的账号，本脚本仅每日一次签到、不代理模型流量。
"""
import json
import os
import sys
import uuid
import urllib.error
import urllib.request

API_BASE = "https://lobsterai-server.youdao.com"
VERSION_API = "https://api-overmind.youdao.com/openapi/get/luna/hardware/lobsterai/prod/update"
TIMEOUT = 25


def _req(url, token=None, method="GET", body=None):
    h = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"raw": ""}
    except Exception as e:
        return -1, {"raw": str(e)[:160]}


def refresh(creds, version):
    body = {
        "firstKeyfrom": creds.get("first_keyfrom", ""),
        "latestKeyfrom": creds.get("latest_keyfrom", ""),
        "version": version,
        "refreshToken": creds.get("refresh_token", ""),
    }
    if creds.get("uuid"):
        body["uuid"] = creds["uuid"]
    if creds.get("user_id"):
        body["userId"] = creds["user_id"]
    st, d = _req(API_BASE + "/api/auth/refresh", method="POST", body=body)
    if st == 200 and isinstance(d, dict):
        data = d.get("data") or d
        at = data.get("accessToken") or ""
        rt = data.get("refreshToken") or creds.get("refresh_token")
        if at:
            new = dict(creds)
            new["access_token"] = at
            new["refresh_token"] = rt
            new["expires_at"] = data.get("expiresAt") or creds.get("expires_at")
            return new, ""
    return None, "refresh HTTP %s %s" % (st, str(d)[:160])


def main():
    raw = os.environ.get("LOBSTER_CREDS", "").strip()
    if not raw:
        print(json.dumps({"ok": False, "stage": "config", "msg": "未设置 LOBSTER_CREDS"}, ensure_ascii=False))
        return 2
    try:
        creds = json.loads(raw)
    except Exception:
        print(json.dumps({"ok": False, "stage": "config", "msg": "LOBSTER_CREDS 非法 JSON"}, ensure_ascii=False))
        return 2

    # 0) 版本号
    st, d = _req(VERSION_API)
    version = ((d.get("data") or {}).get("value") or {}).get("version") or ""
    if not version:
        print(json.dumps({"ok": False, "stage": "version", "msg": "版本号获取失败"}, ensure_ascii=False))
        return 1

    tok = creds.get("access_token") or ""
    rotated = False

    # 1) 槽位
    st, d = _req(API_BASE + "/api/client-activities/slot?placement=desktop_sidebar&containerApiVersion=2&platform=win32&clientVersion=%s" % version, tok)
    if st == 401:
        new_creds, err = refresh(creds, version)
        if not new_creds:
            print(json.dumps({"ok": False, "stage": "auth", "msg": "续期失败: %s" % err}, ensure_ascii=False))
            return 4
        out_file = os.environ.get("LOBSTER_NEW_CREDS_FILE", "lobster_new_creds.json")
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(new_creds, f, ensure_ascii=False)
        except Exception:
            pass
        tok = new_creds["access_token"]
        rotated = True
        st, d = _req(API_BASE + "/api/client-activities/slot?placement=desktop_sidebar&containerApiVersion=2&platform=win32&clientVersion=%s" % version, tok)

    if st == 403:
        msg = (d or {}).get("message") or str(d)[:160]
        print(json.dumps({"ok": False, "stage": "slot", "state": "restricted", "msg": msg}, ensure_ascii=False))
        return 1
    if st != 200 or not isinstance(d, dict):
        print(json.dumps({"ok": False, "stage": "slot", "msg": "HTTP %s %s" % (st, str(d)[:160])}, ensure_ascii=False))
        return 1

    slot = d.get("data") or {}
    # 实际响应把活动信息嵌在 data.activity 下（顶层同名键作为兼容兜底）
    act = slot.get("activity") or {}
    code = act.get("activityCode") or slot.get("activityCode") or ""
    rev = act.get("configRevision") if act.get("configRevision") is not None else slot.get("configRevision")
    slot_state = slot.get("slotState") or act.get("slotState")
    if slot_state != "available" or not code:
        print(json.dumps({"ok": True, "state": "inactive", "slotState": slot_state, "rotated": rotated}, ensure_ascii=False))
        return 0

    # 2) 上下文
    st, d = _req(API_BASE + "/api/client-activities/%s/context?configRevision=%s" % (code, rev), tok)
    if st != 200 or not isinstance(d, dict):
        print(json.dumps({"ok": False, "stage": "context", "msg": "HTTP %s %s" % (st, str(d)[:160])}, ensure_ascii=False))
        return 1
    ctx = d.get("data") or {}
    state = ctx.get("state") or {}
    claimed = ctx.get("claimedToday")
    if claimed is None:
        claimed = state.get("claimedToday")
    if claimed:
        print(json.dumps({"ok": True, "state": "already", "credit": state.get("rewardCredits"), "rotated": rotated}, ensure_ascii=False))
        return 0
    if "check_in" not in (ctx.get("actions") or []):
        print(json.dumps({"ok": True, "state": "inactive", "rotated": rotated}, ensure_ascii=False))
        return 0

    # 3) 签到
    body = {"configRevision": rev, "idempotencyKey": str(uuid.uuid4()), "payload": {}}
    st, d = _req(API_BASE + "/api/client-activities/%s/actions/check_in" % code, tok, "POST", body)
    if st != 200 or not isinstance(d, dict):
        print(json.dumps({"ok": False, "stage": "claim", "msg": "HTTP %s %s" % (st, str(d)[:160])}, ensure_ascii=False))
        return 1
    result = ((d.get("data") or {}).get("result")) or {}
    credit = next((result.get(k) for k in ("creditsGranted", "rewardCredits", "credits")
                   if isinstance(result.get(k), (int, float))), 0)
    print(json.dumps({"ok": True, "state": "claimed", "credit": credit, "rotated": rotated}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
