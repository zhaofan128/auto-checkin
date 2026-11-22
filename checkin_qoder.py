#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qoder / Qoder CN 每日签到（100 Credits/天，幂等）。

凭据从环境变量读取：
  QODER_CN_TOKEN      Qoder CN 凭据（见下），支持滚动续期
  QODER_GLOBAL_TOKEN  Qoder 国际版令牌（可选，dt-... 直接使用）
QODER_CN_TOKEN 支持：
  pt-...           个人访问令牌，首次通过 /api/v1/jobToken/exchange 换成 job token
  dt-...           security_oauth_token，直接使用
  其他             上一次写回的 refresh token，走 /api/v1/jobToken/refresh 续期
每次续期后会把新的 refresh token 写入 qoder_new_token.txt，由 Actions 写回 Secret，
因此 PAT 过期后仍能一直滚动，无需手动更换。
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


def _job_token(d):
    return str(d.get("token") or d.get("access_token") or d.get("device_token") or "").strip()


def resolve_token(base, value):
    """把凭据换成 job token；返回 (token, 新凭据 JSON 或 None, error)。"""
    value = (value or "").strip()
    refresh, pat = "", ""
    if value.startswith("{"):
        try:
            d = json.loads(value)
        except ValueError:
            return None, None, "Qoder 凭据 JSON 解析失败"
        refresh = str(d.get("refresh_token") or "").strip()
        pat = str(d.get("pat") or d.get("personal_token") or "").strip()
    elif value.startswith("pt-"):
        pat = value
    elif value.startswith("dt-"):
        return value, None, None
    else:
        refresh = value

    errors = []
    if refresh:
        st, d = _call(base, "/api/v1/jobToken/refresh", "", "POST", {"refresh_token": refresh})
        if st == 200 and isinstance(d, dict) and _job_token(d):
            cred = {"refresh_token": str(d.get("refresh_token") or refresh).strip()}
            if pat:
                cred["pat"] = pat
            return _job_token(d), json.dumps(cred), None
        errors.append("刷新令牌失败: HTTP %s %s" % (st, str(d)[:120]))

    if pat:
        st, d = _call(base, "/api/v1/jobToken/exchange", "", "POST", {"personal_token": pat})
        if st == 200 and isinstance(d, dict) and _job_token(d):
            cred = {"refresh_token": str(d.get("refresh_token") or "").strip(), "pat": pat}
            return _job_token(d), json.dumps(cred), None
        errors.append("个人访问令牌换取 job token 失败: HTTP %s %s" % (st, str(d)[:120]))

    if not errors:
        errors.append("未提供有效凭据")
    return None, None, "；".join(errors)


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
        resolved, new_cred, err = resolve_token(base, token)
        if err:
            results.append({"label": label, "ok": False, "error": err})
            continue
        # 先落盘再签到，避免签到异常时丢掉已经轮换的新凭据
        if new_cred and label == "Qoder CN":
            with open("qoder_new_token.txt", "w", encoding="utf-8") as f:
                f.write(new_cred + "\n")
        results.append(do(base, resolved, label))
    ok = all(r["ok"] for r in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
