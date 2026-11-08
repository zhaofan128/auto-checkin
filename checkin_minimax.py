#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MiniMax Code 每日签到（一轮 7 天：400/400/400/1000/400/400/1000 = 4000 积分，30 天有效）。

凭据从环境变量 MM_CREDS 读取（JSON：access_token / refresh_token / expires_at）。
协议（实测）：只需 Bearer，无需签名头。
  GET  {host}/minimax-cloud/api/v1/signin/status?timezone_id=Asia/Shanghai
  POST {host}/minimax-cloud/api/v1/signin/claim?timezone_id=Asia/Shanghai   body {}
  领取结果 claim_result：1=本次真领取，2=今日已领。
令牌续期：POST {account}/oauth2/token  grant_type=refresh_token。
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_HOST = "https://agent.minimax.cn"
ACCOUNT_HOST = "https://account.minimax.cn"
CLIENT_ID = "mcode-public"
TZ = "Asia/Shanghai"
TIMEOUT = 25


def _req(url, token=None, method="GET", body=None):
    headers = {"Accept": "application/json", "User-Agent": "MiniMaxCheckin/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {"raw": ""}
    except Exception as e:
        return -1, {"raw": str(e)[:200]}


def refresh(rt):
    st, d = _req(ACCOUNT_HOST + "/oauth2/token", method="POST",
                 body={"grant_type": "refresh_token", "refresh_token": rt,
                       "client_id": CLIENT_ID})
    if st == 200 and isinstance(d, dict):
        at = d.get("access_token") or ""
        nrt = d.get("refresh_token") or rt
        exp = d.get("expires_at") or d.get("expires_in")
        if at:
            return {"access_token": at, "refresh_token": nrt,
                    "expires_at": exp, "token_type": "bearer"}, ""
    return None, "refresh HTTP %s %s" % (st, str(d)[:160])


def signin_status(tok):
    return _req(API_HOST + "/minimax-cloud/api/v1/signin/status?timezone_id=" + TZ, tok)


def signin_claim(tok):
    return _req(API_HOST + "/minimax-cloud/api/v1/signin/claim?timezone_id=" + TZ, tok, "POST", {})


def main():
    raw = os.environ.get("MM_CREDS", "").strip()
    if not raw:
        print(json.dumps({"ok": False, "stage": "config", "msg": "未设置 MM_CREDS"}, ensure_ascii=False))
        return 2
    try:
        creds = json.loads(raw)
    except Exception:
        print(json.dumps({"ok": False, "stage": "config", "msg": "MM_CREDS 非法 JSON"}, ensure_ascii=False))
        return 2

    tok = creds.get("access_token") or ""
    if not tok:
        print(json.dumps({"ok": False, "stage": "config", "msg": "MM_CREDS 缺 access_token"}, ensure_ascii=False))
        return 2

    rotated = False
    st, d = signin_status(tok)
    if st == 401:
        # ⚠️ 刻意**不在这里刷新**：MiniMax 的 refresh_token 是单链的，
        # 云端刷新会把本机 DSH/客户端的令牌顶掉（反之亦然）。
        # access_token 本身有效期约 40 天，过期后重新同步一次即可。
        print(json.dumps({"ok": False, "stage": "auth",
                          "msg": "access_token 已过期，请重新授权后同步（云端不刷新以免顶掉本机令牌）"},
                         ensure_ascii=False))
        return 4

    if st != 200 or not isinstance(d, dict):
        print(json.dumps({"ok": False, "stage": "status", "msg": "HTTP %s %s" % (st, str(d)[:160])}, ensure_ascii=False))
        return 1

    data = d.get("data") or {}
    days = data.get("days") or []
    today = next((x for x in days if x.get("is_today")), None)
    out = {"ok": True, "scene": data.get("scene"),
           "today_points": (today or {}).get("points"),
           "day_no": (today or {}).get("day_no"),
           "rotated": rotated}

    status = (today or {}).get("status")  # 1=未开始 2=可领 3=已领
    if status == 2:
        cst, cd = signin_claim(tok)
        cdata = (cd or {}).get("data") or {}
        cr = cdata.get("claim_result")
        out["state"] = "claimed" if cr == 1 else ("already" if cr == 2 else "claim_unknown")
        out["claim_result"] = cr
        out["ok"] = cr in (1, 2)
    elif status == 3:
        out["state"] = "already"
    else:
        out["state"] = "pending"
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
