#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 每日签到 + 派 Buddy 旅行。长效令牌从环境变量 WB_RT 读取。"""
import json
import os
import random
import sys
import urllib.error
import urllib.request

RT = os.environ.get("WB_RT", "").strip()

PLUGIN = "https://copilot.tencent.com"
REFRESH = "/v2/plugin/auth/token/refresh"
BILLING = "https://www.codebuddy.cn/v2"
STATUS = "/billing/meter/checkin-activity-status"
CHECKIN = "/billing/meter/daily-checkin"
TRAVEL = "https://www.workbuddy.cn"
T_STATUS = "/activity/growth/buddy/travel/status"
T_CONFIG = "/activity/growth/buddy/travel/config"
T_CLAIM = "/activity/growth/buddy/travel/claim"
T_DEPART = "/activity/growth/buddy/travel/depart"
UA = "WorkBuddy-Checkin-Script/1.1"
TIMEOUT = 25


def _read(resp):
    raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw[:300]}


def call(base, path, token, payload=None, method="POST"):
    data = None
    if not (method == "GET" and payload is None):
        data = json.dumps(payload if payload is not None else {}).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, _read(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, _read(e)
        except Exception:
            return e.code, {"raw": ""}
    except Exception as e:
        return -1, {"raw": str(e)[:200]}


def refresh(rt):
    req = urllib.request.Request(PLUGIN + REFRESH, data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Refresh-Token", rt)
    req.add_header("X-Auth-Refresh-Source", "plugin")
    req.add_header("X-Domain", "copilot.tencent.com")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"code": -1, "msg": "HTTP %s" % e.code}
    except Exception as e:
        return {"code": -1, "msg": str(e)[:200]}


def mask(t):
    return (t[:6] + "..." + t[-4:]) if len(t) > 14 else "***"


def main():
    if not RT:
        print(json.dumps({"ok": False, "stage": "config", "msg": "WB_RT 未设置"}, ensure_ascii=False))
        return 2
    r = refresh(RT)
    if r.get("code") != 0 or not isinstance(r.get("data"), dict):
        print(json.dumps({"ok": False, "stage": "refresh", "code": r.get("code"),
                          "msg": r.get("msg")}, ensure_ascii=False))
        return 2
    at = r["data"].get("accessToken") or ""
    if not at:
        print(json.dumps({"ok": False, "stage": "refresh", "msg": "no accessToken"}, ensure_ascii=False))
        return 2
    out = {"ok": True, "token": mask(at)}

    _st, body = call(BILLING, STATUS, at)
    d = body.get("data") if isinstance(body, dict) else {}
    d = d if isinstance(d, dict) else {}
    out["balance"] = d.get("total_credits") or d.get("balance")
    if d.get("today_checked_in") is True:
        out["checkin"] = "already"
    else:
        c2, b2 = call(BILLING, CHECKIN, at)
        code = str((b2 or {}).get("code", ""))
        m = (b2 or {}).get("msg") or ""
        if code == "10001" or "已签到" in m or "今天已签到" in m:
            out["checkin"] = "already"
        elif 200 <= c2 < 300 and code in ("", "0", "200"):
            out["checkin"] = "claimed"
            out["credit"] = b2.get("credit") or (b2.get("data") or {}).get("credit")
            out["streak"] = b2.get("streak_days") or (b2.get("data") or {}).get("streak_days")
            nb = (b2.get("data") or {}).get("total_credits") or (b2.get("data") or {}).get("balance")
            if nb:
                out["balance"] = nb
        else:
            out["ok"] = False
            out["checkin"] = "failed"
            out["checkin_msg"] = m or ("HTTP %s code=%s" % (c2, code))

    tv = {}
    _ts, tb = call(TRAVEL, T_STATUS, at, method="GET")
    s = (tb or {}).get("data") if isinstance(tb, dict) and tb.get("code") == 0 else None
    if not isinstance(s, dict):
        tv["available"] = False
    else:
        tv["available"] = True

        def snap():
            tv["state"] = s.get("state")
            tv["location"] = (s.get("location") or {}).get("name")
            tv["reward"] = s.get("reward_credit")

        snap()
        if s.get("state") == "arrived":
            cs, cb = call(TRAVEL, T_CLAIM, at, payload={})
            tv["claim"] = "ok" if (cs == 200 and (cb or {}).get("code") == 0) else (
                (cb or {}).get("msg") or ("HTTP %s" % cs))
            _ts2, tb2 = call(TRAVEL, T_STATUS, at, method="GET")
            s = (tb2 or {}).get("data") if isinstance(tb2, dict) and tb2.get("code") == 0 else s
            snap()
        if s.get("daily_limit_reached"):
            tv["depart"] = "daily_limit_reached"
        elif s.get("state") in (None, "", "idle"):
            _cs, cb = call(TRAVEL, T_CONFIG, at, method="GET")
            locs = ((cb or {}).get("data") or {}).get("locations") or []
            ids = [x.get("id") for x in locs if isinstance(x, dict) and x.get("id") is not None]
            if not ids:
                tv["depart"] = "no_location"
            else:
                lid = random.choice(ids)
                ds, db = call(TRAVEL, T_DEPART, at, payload={"location_id": lid})
                if ds == 200 and (db or {}).get("code") == 0:
                    tv["depart"] = (((db.get("data") or {}).get("location") or {}).get("name")
                                    or ("地点%s" % lid))
                else:
                    tv["depart"] = "failed:" + str((db or {}).get("msg") or ds)
        else:
            tv["depart"] = "traveling"

    out["travel"] = tv
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
