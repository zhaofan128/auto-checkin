#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qoder / Qoder CN 每日签到（100 Credits/天，幂等）。

凭据从环境变量读取：
  QODER_CN_TOKEN      Qoder CN 的 security_oauth_token（dt-...）或个人访问令牌（pt-...）
  QODER_GLOBAL_TOKEN  Qoder 国际版令牌（可选，同上）
pt- 开头的个人访问令牌会先通过 /api/v1/jobToken/exchange 换成 job token（jt-...），
再用于签到；dt- 令牌直接使用。
协议：GET /sash/api/v1/me/campaigns 找到 CLAIM_BENEFIT 且 CLAIMABLE 的活动，
      POST /sash/api/v1/me/campaigns/{id}/claim 领取（服务端幂等，重复返回 replayed）。
"""
import json
import os
import sys
import urllib.error
import urllib.request

UA = "Qoder/claim"
TIMEOUT = 25


def _call(base, path, token, method="GET", body=None):
    headers = {"Cosy-ClientType": "10", "User-Agent": UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
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


def resolve_token(base, value):
    """pt- 个人访问令牌先换成 job token；返回 (token, error)。"""
    if not value.startswith("pt-"):
        return value, None
    st, d = _call(base, "/api/v1/jobToken/exchange", "", "POST", {"personal_token": value})
    if st != 200 or not isinstance(d, dict):
        return None, "个人访问令牌换取 job token 失败: HTTP %s %s" % (st, str(d)[:160])
    token = str(d.get("token") or d.get("access_token") or d.get("device_token") or "").strip()
    if not token:
        return None, "个人访问令牌换取 job token 失败: 响应中没有 token"
    return token, None


def do(base, token, label):
    out = {"label": label, "ok": False}
    st, d = _call(base, "/sash/api/v1/me/campaigns", token)
    if st != 200 or not isinstance(d, dict):
        out["error"] = "HTTP %s %s" % (st, str(d)[:160])
        return out
    campaigns = d.get("campaigns") or []
    benefit = [c for c in campaigns if c.get("actionType") == "CLAIM_BENEFIT"]
    if not benefit:
        out["ok"] = True
        out["state"] = "无签到活动"
        return out
    c = benefit[0]
    out["campaign"] = c.get("campaignKey")
    if c.get("claimStatus") == "CLAIMABLE":
        st2, d2 = _call(base, "/sash/api/v1/me/campaigns/%s/claim" % c["campaignId"], token, "POST", {})
        out["state"] = "claimed" if st2 == 200 else "failed"
        out["resp"] = json.dumps(d2, ensure_ascii=False)[:160] if st2 != 200 else "ok"
        out["ok"] = (st2 == 200)
    else:
        out["state"] = "already"
        out["ok"] = True
    return out


def main():
    results = []
    cn = os.environ.get("QODER_CN_TOKEN", "").strip()
    gl = os.environ.get("QODER_GLOBAL_TOKEN", "").strip()
    if not cn and not gl:
        print(json.dumps({"ok": False, "stage": "config", "msg": "未设置 Qoder 令牌"}, ensure_ascii=False))
        return 2
    for base, token, label in (("https://openapi.qoder.com.cn", cn, "Qoder CN"),
                               ("https://openapi.qoder.sh", gl, "Qoder Global")):
        if not token:
            continue
        resolved, err = resolve_token(base, token)
        results.append({"label": label, "ok": False, "error": err} if err else do(base, resolved, label))
    ok = all(r["ok"] for r in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
