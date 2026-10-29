#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub API 封装：用户/仓库、Secrets 写入（sealed box）、运行记录、手动触发。"""
import base64
import json
import urllib.error
import urllib.request

import nacl.encoding
import nacl.public

API = "https://api.github.com"
UA = "AutoCheckin-App/1.0"
TIMEOUT = 30


class GitHubError(Exception):
    pass


def _req(method, url, token, payload=None, raw=False, follow=True):
    data = None
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if follow:
        opener = urllib.request.build_opener()
    else:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read()
            return r.status, (body if raw else (json.loads(body) if body else {}))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303) and e.headers.get("Location"):
            return e.code, e.headers["Location"].encode() if raw else e.headers["Location"]
        body = e.read()
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body[:300].decode("utf-8", "replace")}
        raise GitHubError("HTTP %s: %s" % (e.code, parsed.get("message") or parsed))
    except Exception as e:
        raise GitHubError(str(e))


def get_login(token):
    st, d = _req("GET", API + "/user", token)
    if st != 200:
        raise GitHubError("令牌无效或网络异常（HTTP %s）" % st)
    return d.get("login", "")


def repo_info(token, owner, repo):
    st, d = _req("GET", "%s/repos/%s/%s" % (API, owner, repo), token)
    if st != 200:
        raise GitHubError("仓库 %s/%s 不可访问（HTTP %s）" % (owner, repo, st))
    return d


def list_secrets(token, owner, repo):
    st, d = _req("GET", "%s/repos/%s/%s/actions/secrets" % (API, owner, repo), token)
    if st != 200:
        raise GitHubError("读取 Secrets 失败（HTTP %s）" % st)
    return {s["name"]: s.get("updated_at", "") for s in d.get("secrets", [])}


def set_secret(token, owner, repo, name, value):
    st, d = _req("GET", "%s/repos/%s/%s/actions/secrets/public-key" % (API, owner, repo), token)
    if st != 200:
        raise GitHubError("获取仓库公钥失败（HTTP %s）" % st)
    pk = nacl.public.PublicKey(d["key"].encode("utf-8"), nacl.encoding.Base64Encoder())
    sealed = nacl.public.SealedBox(pk).encrypt(value.encode("utf-8"))
    payload = {"encrypted_value": base64.b64encode(sealed).decode("ascii"),
               "key_id": d["key_id"]}
    st, _ = _req("PUT", "%s/repos/%s/%s/actions/secrets/%s" % (API, owner, repo, name), token, payload)
    if st not in (201, 204):
        raise GitHubError("写入 Secret %s 失败（HTTP %s，令牌需要 repo 权限）" % (name, st))


def dispatch(token, owner, repo, workflow="checkin.yml", ref="main"):
    url = "%s/repos/%s/%s/actions/workflows/%s/dispatches" % (API, owner, repo, workflow)
    st, _ = _req("POST", url, token, {"ref": ref})
    if st != 204:
        raise GitHubError("触发失败（HTTP %s）——检查 workflow 是否存在且默认分支为 %s" % (st, ref))


def latest_runs(token, owner, repo, per_page=10):
    st, d = _req("GET", "%s/repos/%s/%s/actions/workflows/checkin.yml/runs?per_page=%d"
                 % (API, owner, repo, per_page), token)
    if st != 200:
        raise GitHubError("读取运行记录失败（HTTP %s）" % st)
    runs = []
    for r in d.get("workflow_runs", []):
        runs.append({"id": r["id"], "created": r["created_at"], "status": r["status"],
                     "conclusion": r["conclusion"], "event": r.get("event", "")})
    return runs


def run_jobs(token, owner, repo, run_id):
    st, d = _req("GET", "%s/repos/%s/%s/actions/runs/%s/jobs" % (API, owner, repo, run_id), token)
    if st != 200:
        raise GitHubError("读取作业失败（HTTP %s）" % st)
    return [(j["name"], j["conclusion"] or j["status"]) for j in d.get("jobs", [])]


def job_result_json(token, owner, repo, run_id, keyword):
    """从指定关键字的 job 日志里抓最后一行 JSON 结果。找不到返回 None。"""
    st, d = _req("GET", "%s/repos/%s/%s/actions/runs/%s/jobs" % (API, owner, repo, run_id), token)
    if st != 200:
        return None
    for j in d.get("jobs", []):
        if keyword not in j["name"]:
            continue
        url = "%s/repos/%s/%s/actions/jobs/%s/logs" % (API, owner, repo, j["id"])
        st2, loc = _req("GET", url, token, raw=True, follow=False)
        if st2 in (301, 302, 303) and loc:
            # 重定向到 blob 存储，不能再带认证头
            req2 = urllib.request.Request(loc.decode() if isinstance(loc, bytes) else loc,
                                          headers={"User-Agent": UA})
            with urllib.request.urlopen(req2, timeout=TIMEOUT) as r:
                raw = r.read()
        elif st2 == 200:
            raw = loc
        else:
            return None
        for line in raw.decode("utf-8", "replace").splitlines():
            if '"ok"' in line:
                idx = line.find("{")
                if idx >= 0:
                    try:
                        return json.loads(line[idx:])
                    except Exception:
                        pass
    return None
