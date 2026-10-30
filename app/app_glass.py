#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoCheckin · 液态玻璃版 —— pywebview + HTML/CSS 前端，Python 后端。

相比旧版：自动加载本机 Token、一键开启、果冻开关控制平台启停、状态仪表盘。
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import traceback
import webbrowser
from contextlib import redirect_stdout

import webview

import ghapi
import wbcreds

APP_TITLE = "AutoCheckin"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AutoCheckin")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOCAL_TOKEN_FILE = r"C:\Users\Administrator\.workbuddy\gh-secrets\gh_oauth_token.txt"  # 本助手自用


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def load_config():
    try:
        with io.open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with io.open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _run_module(path, env):
    """隔离运行签到脚本，返回 (code, stdout文本, 附加轮换文件)。"""
    tmp = tempfile.mkdtemp(prefix="autocheckin-")
    name = "chk_%d_%s" % (os.getpid(), os.path.basename(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    keys = list(env) + ["WB_NEW_RT_FILE", "TRAE_NEW_CREDS_FILE"]
    old_env = {k: os.environ.get(k) for k in keys}
    old_cwd = os.getcwd()
    buf = io.StringIO()
    code = 0
    try:
        os.chdir(tmp)
        os.environ.update(env)
        os.environ["WB_NEW_RT_FILE"] = os.path.join(tmp, "wb_new_rt.txt")
        os.environ["TRAE_NEW_CREDS_FILE"] = os.path.join(tmp, "trae_new_creds.json")
        with redirect_stdout(buf):
            spec.loader.exec_module(mod)
            code = mod.main()
    finally:
        os.chdir(old_cwd)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    extra = {}
    for f in ("wb_new_rt.txt", "trae_new_creds.json"):
        p = os.path.join(tmp, f)
        if os.path.isfile(p):
            try:
                extra[f] = io.open(p, encoding="utf-8").read().strip()
            except Exception:
                pass
    return code, buf.getvalue().strip(), extra


def _parse_json_line(text):
    for line in reversed(text.splitlines()):
        idx = line.find("{")
        if idx >= 0:
            try:
                return json.loads(line[idx:])
            except Exception:
                continue
    return None


class Api:
    def __init__(self):
        self.cfg = load_config()
        self.creds = {}

    # ---------- 凭据校验（顺带轮换，保证写进 Secret 的是最新一份） ----------
    def _validate_wb(self, rt):
        """返回 (可用?, 最新令牌或None, 错误说明)。"""
        if not rt:
            return False, None, "本机未找到 WorkBuddy 令牌"
        try:
            new_rt, err = wbcreds.wb_refresh(rt)
            if new_rt:
                return True, new_rt, ""
            return False, None, "WorkBuddy 令牌失效：%s（请在 WorkBuddy 客户端重新登录）" % err
        except Exception as e:
            return False, None, "WorkBuddy 令牌校验失败：%s" % e

    def _trae_module(self):
        path = os.path.join(base_dir(), "runners", "checkin_trae.py")
        spec = importlib.util.spec_from_file_location("trae_probe_%d" % id(path), path)
        mod = importlib.util.module_from_spec(spec)
        return spec, mod

    def _validate_trae(self, creds_json):
        """尝试续期一次；成功则返回 (True, 轮换后的最新 creds json, "")。"""
        if not creds_json:
            return False, None, "本机未找到 TraeWork 登录态"
        tmp = tempfile.mkdtemp(prefix="trae-probe-")
        out_file = os.path.join(tmp, "trae_new_creds.json")
        old = {k: os.environ.get(k) for k in ("TRAE_CREDS", "TRAE_NEW_CREDS_FILE")}
        try:
            os.environ["TRAE_CREDS"] = creds_json
            os.environ["TRAE_NEW_CREDS_FILE"] = out_file
            spec, mod = self._trae_module()
            spec.loader.exec_module(mod)
            token, note = mod.refresh()
            if token:
                if os.path.isfile(out_file):
                    return True, io.open(out_file, encoding="utf-8").read().strip(), ""
                return True, creds_json, ""
            msg = str(note)
            if "20101" in msg or "invalid" in msg.lower():
                return False, None, "TraeWork 令牌已被客户端轮换失效，请在 TraeWork 里重新登录一次"
            return False, None, "TraeWork 续期失败：%s" % msg[:120]
        except Exception as e:
            return False, None, "TraeWork 校验异常：%s" % e
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # ---------- 内部 ----------
    def _token(self):
        return (self.cfg.get("token") or "").strip()

    def _ctx(self):
        token = self._token()
        if not token:
            raise ghapi.GitHubError("未保存 GitHub Token")
        owner = (self.cfg.get("owner") or "").strip()
        repo = (self.cfg.get("repo") or "auto-checkin").strip()
        if not owner:
            owner = ghapi.get_login(token)
            self.cfg["owner"] = owner
            save_config(self.cfg)
        return token, owner, repo

    def _extract_creds(self):
        out = {}
        rt = wbcreds.wb_rt()
        if rt:
            new_rt, err = wbcreds.wb_refresh(rt)
            out["WB_RT"] = new_rt or rt
        else:
            out["WB_RT"] = ""
        # Trae：优先用本 App 自己维护的令牌链（避免客户端没打开、storage 里的旧环已失效）
        chain = os.path.join(CONFIG_DIR, "trae_chain.json")
        creds = None
        if os.path.isfile(chain):
            try:
                creds = json.load(io.open(chain, encoding="utf-8"))
            except Exception:
                creds = None
        if not creds:
            creds, _name = wbcreds.trae_creds()
        out["TRAE_CREDS"] = json.dumps(creds, ensure_ascii=False) if creds else ""
        self.creds = out
        return out

    def _save_chain(self, creds_json):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with io.open(os.path.join(CONFIG_DIR, "trae_chain.json"), "w", encoding="utf-8") as f:
                f.write(creds_json)
        except Exception:
            pass

    # ---------- JS API ----------
    def boot(self):
        """启动即调：本地自动发现 token，返回整体状态。"""
        res = {"token_ok": False, "owner": "", "repo": "", "secrets": {},
               "configured": False}
        token = self._token()
        if not token and os.path.isfile(LOCAL_TOKEN_FILE):
            try:
                token = io.open(LOCAL_TOKEN_FILE, encoding="utf-8").read().strip()
            except Exception:
                token = ""
        if token:
            self.cfg["token"] = token
            try:
                res["owner"] = ghapi.get_login(token)
                self.cfg["owner"] = res["owner"]
                res["token_ok"] = True
                save_config(self.cfg)
            except Exception:
                pass
        res["repo"] = self.cfg.get("repo") or "auto-checkin"
        if res["token_ok"]:
            try:
                token, owner, repo = self._ctx()
                res["secrets"] = ghapi.list_secrets(token, owner, repo)
                res["configured"] = ("WB_RT" in res["secrets"]) or ("TRAE_CREDS" in res["secrets"])
            except Exception:
                pass
        return res

    def one_click(self):
        """一键开启：提取 → 校验/续期 → 写入 Secrets（含开关默认开）。"""
        steps = []
        try:
            token, owner, repo = self._ctx()
            steps.append("已连接 %s/%s" % (owner, repo))
        except Exception as e:
            return {"ok": False, "steps": steps, "error": str(e)}
        try:
            creds = self._extract_creds()
        except Exception as e:
            return {"ok": False, "steps": steps, "error": "凭据提取失败：%s" % e}

        wb_ok, wb_rt, wb_err = self._validate_wb(creds.get("WB_RT"))
        trae_ok, trae_creds, trae_err = self._validate_trae(creds.get("TRAE_CREDS"))

        try:
            if wb_ok:
                ghapi.set_secret(token, owner, repo, "WB_RT", wb_rt)
                ghapi.set_secret(token, owner, repo, "WB_ENABLED", "true")
                steps.append("WorkBuddy 令牌有效，已写入（顺带续期 30 天）")
            else:
                steps.append("⚠ %s" % wb_err)
            if trae_ok:
                ghapi.set_secret(token, owner, repo, "TRAE_CREDS", trae_creds)
                ghapi.set_secret(token, owner, repo, "TRAE_ENABLED", "true")
                steps.append("TraeWork 令牌有效，已写入（已轮换为最新一份）")
            else:
                steps.append("⚠ %s" % trae_err)
            ghapi.set_secret(token, owner, repo, "GH_PAT", token)
            steps.append("自动轮换密钥已配置")
        except Exception as e:
            return {"ok": False, "steps": steps, "error": "写入 Secrets 失败：%s" % e}
        return {"ok": wb_ok and trae_ok, "steps": steps, "wb": wb_ok, "trae": trae_ok,
                "partial": (wb_ok != trae_ok)}

    def set_enabled(self, platform, enabled):
        """果冻开关回调：WB / TRAE 的云端启停。"""
        try:
            token, owner, repo = self._ctx()
            name = ("WB_ENABLED" if platform == "wb" else "TRAE_ENABLED")
            ghapi.set_secret(token, owner, repo, name, "true" if enabled else "false")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def checkin_local(self):
        """本机直签（幂等），返回两个平台的 JSON 结果；轮换出的新令牌会同步回 Secret，
        避免本机与云端各持一环、互相把对方刷废。"""
        res = {}
        try:
            self._extract_creds()
        except Exception as e:
            return {"ok": False, "error": "凭据提取失败：%s" % e}
        rotated = {}
        if self.creds.get("WB_RT"):
            try:
                code, txt, extra = _run_module(
                    os.path.join(base_dir(), "runners", "checkin_wb.py"),
                    {"WB_RT": self.creds["WB_RT"]})
                res["wb"] = _parse_json_line(txt) or {"ok": False, "raw": txt[-200:]}
                res["wb"]["_code"] = code
                if "wb_new_rt.txt" in extra:
                    self.creds["WB_RT"] = extra["wb_new_rt.txt"]
                    rotated["WB_RT"] = extra["wb_new_rt.txt"]
            except Exception as e:
                res["wb"] = {"ok": False, "error": str(e)}
        if self.creds.get("TRAE_CREDS"):
            try:
                code, txt, extra = _run_module(
                    os.path.join(base_dir(), "runners", "checkin_trae.py"),
                    {"TRAE_CREDS": self.creds["TRAE_CREDS"]})
                res["trae"] = _parse_json_line(txt) or {"ok": False, "raw": txt[-200:]}
                res["trae"]["_code"] = code
                if "trae_new_creds.json" in extra:
                    self.creds["TRAE_CREDS"] = extra["trae_new_creds.json"]
                    rotated["TRAE_CREDS"] = extra["trae_new_creds.json"]
                    self._save_chain(extra["trae_new_creds.json"])
            except Exception as e:
                res["trae"] = {"ok": False, "error": str(e)}
        # 轮换回写：保证云端用的是最新一环
        if rotated:
            try:
                token, owner, repo = self._ctx()
                for name, val in rotated.items():
                    ghapi.set_secret(token, owner, repo, name, val)
                res["_synced"] = list(rotated.keys())
            except Exception as e:
                res["_sync_error"] = str(e)
        res["ok"] = bool(res.get("wb", {}).get("ok") or res.get("trae", {}).get("ok"))
        return res

    def dispatch_cloud(self):
        try:
            token, owner, repo = self._ctx()
            ghapi.dispatch(token, owner, repo)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def sync_trae(self):
        """从本机 TraeWork 客户端重新提取令牌，**验证有效后**再写入 Secret。"""
        try:
            token, owner, repo = self._ctx()
            creds, name = wbcreds.trae_creds()
            if not creds:
                return {"ok": False, "error": "本机未找到 TraeWork 登录态，请先打开客户端登录一次"}
            ok, latest, err = self._validate_trae(json.dumps(creds, ensure_ascii=False))
            if not ok:
                return {"ok": False, "error": err}
            ghapi.set_secret(token, owner, repo, "TRAE_CREDS", latest)
            ghapi.set_secret(token, owner, repo, "TRAE_ENABLED", "true")
            self._save_chain(latest)
            return {"ok": True, "source": name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_runs(self):
        """云端最近运行 + 每次两个平台的 JSON 结果摘要。"""
        try:
            token, owner, repo = self._ctx()
            runs = ghapi.latest_runs(token, owner, repo, per_page=8)
            out = []
            for r in runs:
                item = {"id": r["id"], "created": r["created"],
                        "conclusion": r["conclusion"], "status": r["status"], "event": r["event"]}
                try:
                    jb = ghapi.run_jobs(token, owner, repo, r["id"])
                    for jname, jstate in jb:
                        if "WorkBuddy" in jname:
                            item["wb_state"] = jstate
                        elif "Trae" in jname:
                            item["trae_state"] = jstate
                    if r["conclusion"]:
                        item["wb"] = ghapi.job_result_json(token, owner, repo, r["id"], "WorkBuddy")
                        item["trae"] = ghapi.job_result_json(token, owner, repo, r["id"], "Trae")
                except Exception:
                    pass
                out.append(item)
            # 自动修复：Trae 令牌链被客户端刷新打断时，自动从本地重新同步一次
            healed = None
            latest = next((x for x in out if x["conclusion"]), None)
            if latest and latest.get("trae") and latest["trae"].get("ok") is False:
                msg = str(latest["trae"].get("msg", ""))
                if "20101" in msg or "invalid" in msg.lower():
                    r = self.sync_trae()
                    healed = {"ok": r.get("ok"), "error": r.get("error")}
            return {"ok": True, "runs": out, "healed": healed,
                    "url": "https://github.com/%s/%s/actions" % (owner, repo)}
        except Exception as e:
            return {"ok": False, "error": str(e), "runs": []}

    def save_token(self, token):
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "Token 为空"}
        try:
            login = ghapi.get_login(token)
        except Exception as e:
            return {"ok": False, "error": "Token 无效：%s" % e}
        self.cfg.update({"token": token, "owner": login})
        save_config(self.cfg)
        return {"ok": True, "owner": login}

    def open_url(self, url):
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        return {"ok": True}


def _excepthook(exc_type, exc, tb):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with io.open(os.path.join(CONFIG_DIR, "error.log"), "a", encoding="utf-8") as f:
            traceback.print_exception(exc_type, exc, tb, file=f)
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    api = Api()
    html = os.path.join(base_dir(), "glass.html")
    webview.create_window(APP_TITLE, html, js_api=api, width=980, height=760,
                          min_size=(860, 640),
                          background_color="#0b0d16")
    webview.start()


if __name__ == "__main__":
    main()
