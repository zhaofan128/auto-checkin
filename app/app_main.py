#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoCheckin 签到助手 —— Windows 桌面小工具。

功能：提取本机凭据 → 写入 GitHub Secrets → 查看云端签到记录 → 云端/本机立即签到。
配合 GitHub 仓库 auto-checkin 的 Actions 定时任务使用。
"""
import importlib.util
import io
import json
import os
import queue
import sys
import threading
import webbrowser
from contextlib import redirect_stdout

import tkinter as tk
from tkinter import messagebox, ttk

import ghapi
import wbcreds

APP_TITLE = "AutoCheckin 签到助手"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AutoCheckin")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


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


def run_module(path, env):
    """在子进程式隔离环境中执行一个签到脚本，返回 (exit_code, 输出文本, 附加文件)。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="autocheckin-")
    name = "wbchk_%d" % os.getpid()
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    old_env = {k: os.environ.get(k) for k in list(env) + ["WB_NEW_RT_FILE", "TRAE_NEW_CREDS_FILE"]}
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x640")
        self.minsize(760, 560)
        self._q = queue.Queue()
        self._jobs = {}
        self._callbacks = {}
        self.creds = {}

        cfg = load_config()
        self.token_var = tk.StringVar(value=cfg.get("token", ""))
        self.repo_var = tk.StringVar(value=cfg.get("repo", "auto-checkin"))
        self.owner_var = tk.StringVar(value=cfg.get("owner", ""))

        self._build_ui()
        self.after(120, self._drain_queue)
        if self.token_var.get():
            self.log("已加载本机保存的 GitHub 令牌（%s…）" % self.token_var.get()[:8])

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="GitHub Token:").pack(side="left")
        self.ent_token = ttk.Entry(top, textvariable=self.token_var, show="*", width=34)
        self.ent_token.pack(side="left", padx=4)
        ttk.Button(top, text="保存并连接", command=self.on_connect).pack(side="left", padx=2)
        ttk.Label(top, text="仓库:").pack(side="left", padx=(14, 0))
        self.ent_owner = ttk.Entry(top, textvariable=self.owner_var, width=14, state="disabled")
        self.ent_owner.pack(side="left", padx=2)
        ttk.Label(top, text="/").pack(side="left")
        self.ent_repo = ttk.Entry(top, textvariable=self.repo_var, width=18)
        self.ent_repo.pack(side="left", padx=2)
        self.lbl_conn = ttk.Label(top, text="未连接", foreground="#888")
        self.lbl_conn.pack(side="left", padx=10)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        # Tab1 凭据与 Secrets
        t1 = ttk.Frame(nb, padding=10)
        nb.add(t1, text=" 凭据与 Secrets ")
        row = ttk.Frame(t1); row.pack(fill="x")
        ttk.Button(row, text="① 提取本机凭据", command=self.on_extract).pack(side="left", padx=2)
        ttk.Button(row, text="② 写入/更新 GitHub Secrets", command=self.on_push_secrets).pack(side="left", padx=2)
        ttk.Button(row, text="查看仓库 Secrets 状态", command=self.on_secret_status).pack(side="left", padx=2)
        self.txt_creds = self._text(t1)

        # Tab2 签到
        t2 = ttk.Frame(nb, padding=10)
        nb.add(t2, text=" 签到 ")
        row2 = ttk.Frame(t2); row2.pack(fill="x")
        ttk.Button(row2, text="☁ 云端立即运行一次", command=self.on_dispatch).pack(side="left", padx=2)
        ttk.Button(row2, text="💻 本机直签（不依赖 GitHub）", command=self.on_local_checkin).pack(side="left", padx=2)
        self.txt_checkin = self._text(t2)

        # Tab3 运行记录
        t3 = ttk.Frame(nb, padding=10)
        nb.add(t3, text=" 云端运行记录 ")
        bar = ttk.Frame(t3); bar.pack(fill="x")
        ttk.Button(bar, text="刷新", command=self.on_refresh_runs).pack(side="left", padx=2)
        ttk.Button(bar, text="打开 Actions 页面", command=lambda: webbrowser.open(
            "https://github.com/%s/%s/actions" % (self.owner_var.get() or "zhaofan128", self.repo_var.get().strip())
        )).pack(side="left", padx=2)
        cols = ("time", "result", "wb", "trae")
        self.tree = ttk.Treeview(t3, columns=cols, show="headings", height=10)
        for c, w, txt in zip(cols, (170, 90, 240, 240), ("时间(北京)", "结论", "WorkBuddy", "TraeWork")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<Double-1>", self.on_run_detail)

        # 日志
        logf = ttk.LabelFrame(self, text="日志", padding=4)
        logf.pack(fill="both", padx=8, pady=(0, 8))
        self.txt_log = self._text(logf, height=7)

    def _text(self, parent, height=None):
        f = ttk.Frame(parent)
        f.pack(fill="both", expand=True, pady=4)
        t = tk.Text(f, wrap="word", font=("Consolas", 10), height=height or 12,
                    background="#1e1e1e", foreground="#d4d4d4", insertbackground="#d4d4d4")
        s = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=s.set)
        s.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        return t

    # ---------- 工具 ----------
    def log(self, msg):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

    def _need_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showinfo(APP_TITLE, "请先在顶部填入 GitHub Token 并保存。")
            return None
        return token

    def _repo(self):
        owner = self.owner_var.get().strip()
        repo = self.repo_var.get().strip()
        if not (owner and repo):
            raise ghapi.GitHubError("仓库未连接，请先点「保存并连接」")
        return owner, repo

    def async_run(self, tag, fn, on_done):
        """后台线程执行 fn()，完成后在主线程回调 on_done(result_or_exc)。"""
        if tag in self._jobs and self._jobs[tag].is_alive():
            self.log("（上一次操作还在进行中，稍等…）")
            return

        def worker():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001
                res = e
            self._q.put((tag, res))

        th = threading.Thread(target=worker, daemon=True)
        self._jobs[tag] = th
        th.start()

    def _drain_queue(self):
        try:
            while True:
                tag, res = self._q.get_nowait()
                cb = self._callbacks.pop(tag, None)
                if cb:
                    cb(res)
        except queue.Empty:
            pass
        self.after(150, self._drain_queue)

    # ---------- 动作 ----------
    def on_connect(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showinfo(APP_TITLE, "请填入 GitHub Token（需要 repo 权限）。")
            return
        self.lbl_conn.config(text="连接中…")

        def job():
            login = ghapi.get_login(token)
            cfg = load_config()
            cfg.update({"token": token, "owner": login,
                        "repo": self.repo_var.get().strip() or "auto-checkin"})
            save_config(cfg)
            return login

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["connect"] = lambda r: self._after_connect(r)
        self.async_run("connect", job, lambda r: None)

    def _after_connect(self, res):
        if isinstance(res, Exception):
            self.lbl_conn.config(text="连接失败", foreground="#c0504d")
            self.log("[连接失败] %s" % res)
            return
        self.owner_var.set(res)
        self.ent_owner.config(state="normal")
        self.lbl_conn.config(text="已连接: %s/%s" % (res, self.repo_var.get().strip()), foreground="#4a7d4a")
        self.log("[OK] 已连接 GitHub 账号 %s，目标仓库 %s/%s" % (res, res, self.repo_var.get().strip()))

    def on_extract(self):
        def job():
            out = {}
            rt = wbcreds.wb_rt()
            if rt:
                new_rt, err = wbcreds.wb_refresh(rt)
                out["WB_RT"] = new_rt or rt
                out["WB_NOTE"] = "已顺带刷新（+30天）" if new_rt else ("刷新失败: %s，使用本地缓存" % err)
            else:
                out["WB_RT"] = ""
                out["WB_NOTE"] = "未找到 ~/.workbuddy/checkin-rt.json（请先登录 WorkBuddy 客户端）"
            creds, name = wbcreds.trae_creds()
            out["TRAE_CREDS"] = json.dumps(creds, ensure_ascii=False) if creds else ""
            out["TRAE_NOTE"] = "来自 %s" % name if creds else "未找到 TraeWork 登录态（请先登录 TraeWork 客户端）"
            return out

        def done(res):
            if isinstance(res, Exception):
                self.log("[提取失败] %s" % res)
                return
            self.creds = res
            self.txt_creds.delete("1.0", "end")
            self.txt_creds.insert("end", "WB_RT      : %s\n" % (res["WB_RT"][:28] + "…" if res["WB_RT"] else "（未获取）"))
            self.txt_creds.insert("end", "             %s\n" % res["WB_NOTE"])
            self.txt_creds.insert("end", "TRAE_CREDS : %s\n" % (res["TRAE_CREDS"][:28] + "…" if res["TRAE_CREDS"] else "（未获取）"))
            self.txt_creds.insert("end", "             %s\n" % res["TRAE_NOTE"])
            self.txt_creds.insert("end", "\n凭据只保存在内存里，点「② 写入 Secrets」后即上传到 GitHub 加密存储。\n")
            self.log("[OK] 本机凭据提取完成")

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["extract"] = done
        self.async_run("extract", job, lambda r: None)

    def on_push_secrets(self):
        token = self._need_token()
        if not token:
            return
        if not self.creds.get("WB_RT") and not self.creds.get("TRAE_CREDS"):
            messagebox.showinfo(APP_TITLE, "请先点「① 提取本机凭据」。")
            return

        def job():
            owner, repo = self._repo()
            done = []
            if self.creds.get("WB_RT"):
                ghapi.set_secret(token, owner, repo, "WB_RT", self.creds["WB_RT"])
                done.append("WB_RT")
            if self.creds.get("TRAE_CREDS"):
                ghapi.set_secret(token, owner, repo, "TRAE_CREDS", self.creds["TRAE_CREDS"])
                done.append("TRAE_CREDS")
            ghapi.set_secret(token, owner, repo, "GH_PAT", token)
            done.append("GH_PAT（用于自动轮换写回）")
            return done

        def done(res):
            if isinstance(res, Exception):
                self.log("[写入失败] %s" % res)
                messagebox.showerror(APP_TITLE, str(res))
                return
            self.log("[OK] Secrets 已写入: %s" % ", ".join(res))
            messagebox.showinfo(APP_TITLE, "Secrets 写入成功：\n" + "\n".join(res))

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["push"] = done
        self.async_run("push", job, lambda r: None)

    def on_secret_status(self):
        token = self._need_token()
        if not token:
            return

        def job():
            owner, repo = self._repo()
            return ghapi.list_secrets(token, owner, repo)

        def done(res):
            if isinstance(res, Exception):
                self.log("[查询失败] %s" % res)
                return
            self.txt_creds.delete("1.0", "end")
            self.txt_creds.insert("end", "仓库 Secrets（只读状态，值不可见）:\n\n")
            for name, ts in sorted(res.items()):
                self.txt_creds.insert("end", "  %-12s %s\n" % (name, ts))

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["secrets"] = done
        self.async_run("secrets", job, lambda r: None)

    def on_dispatch(self):
        token = self._need_token()
        if not token:
            return

        def job():
            owner, repo = self._repo()
            ghapi.dispatch(token, owner, repo)
            return None

        def done(res):
            if isinstance(res, Exception):
                self.log("[触发失败] %s" % res)
                messagebox.showerror(APP_TITLE, str(res))
                return
            self.log("[OK] 已触发云端运行，约 1~2 分钟后可在「云端运行记录」里刷新查看")
            self.on_refresh_runs(delay=45)

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["dispatch"] = done
        self.async_run("dispatch", job, lambda r: None)

    def on_local_checkin(self):
        if not messagebox.askyesno(APP_TITLE,
                                   "将直接在本机调用签到接口（幂等，签过会跳过）。\n继续？"):
            return

        def job():
            self._ensure_creds_for_local()
            out = {}
            if self.creds.get("WB_RT"):
                code, txt, extra = run_module(os.path.join(base_dir(), "runners", "checkin_wb.py"),
                                              {"WB_RT": self.creds["WB_RT"]})
                out["wb"] = {"code": code, "out": txt}
                if "wb_new_rt.txt" in extra:
                    self.creds["WB_RT"] = extra["wb_new_rt.txt"]
            if self.creds.get("TRAE_CREDS"):
                code, txt, extra = run_module(os.path.join(base_dir(), "runners", "checkin_trae.py"),
                                              {"TRAE_CREDS": self.creds["TRAE_CREDS"]})
                out["trae"] = {"code": code, "out": txt}
                if "trae_new_creds.json" in extra:
                    self.creds["TRAE_CREDS"] = extra["trae_new_creds.json"]
            return out

        def done(res):
            if isinstance(res, Exception):
                self.log("[本机签到失败] %s" % res)
                return
            self.txt_checkin.delete("1.0", "end")
            for k in ("wb", "trae"):
                r = res.get(k)
                if r:
                    self.txt_checkin.insert("end", "【%s】exit=%s\n%s\n\n" % (
                        "WorkBuddy" if k == "wb" else "TraeWork", r["code"], r["out"]))
            self.log("[OK] 本机签到执行完成（令牌已顺带滚动续期）")

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["local"] = done
        self.async_run("local", job, lambda r: None)

    def _ensure_creds_for_local(self):
        if not self.creds.get("WB_RT"):
            rt = wbcreds.wb_rt()
            if rt:
                self.creds["WB_RT"] = rt
        if not self.creds.get("TRAE_CREDS"):
            creds, _ = wbcreds.trae_creds()
            if creds:
                self.creds["TRAE_CREDS"] = json.dumps(creds, ensure_ascii=False)
        if not (self.creds.get("WB_RT") or self.creds.get("TRAE_CREDS")):
            raise ghapi.GitHubError("本机没有可用凭据：请先登录 WorkBuddy / TraeWork 客户端")

    def on_refresh_runs(self, delay=0):
        token = self._need_token()
        if not token:
            return

        def job():
            import time
            if delay:
                time.sleep(delay)
            owner, repo = self._repo()
            runs = ghapi.latest_runs(token, owner, repo, per_page=10)
            rows = []
            for r in runs:
                jb = dict(ghapi.run_jobs(token, owner, repo, r["id"]))
                rows.append((r, jb))
            return rows

        def done(res):
            if isinstance(res, Exception):
                self.log("[记录刷新失败] %s" % res)
                return
            self.tree.delete(*self.tree.get_children())
            for r, jb in res:
                wb = next((v for k, v in jb.items() if "WorkBuddy" in k), "-")
                tr = next((v for k, v in jb.items() if "Trae" in k), "-")
                import datetime
                t = datetime.datetime.fromisoformat(r["created"].replace("Z", "+00:00"))
                t = t.astimezone().strftime("%m-%d %H:%M")
                icon = {"success": "✔", "failure": "✘"}.get(r["conclusion"], "…")
                self.tree.insert("", "end", values=(t, "%s %s" % (icon, r["conclusion"] or r["status"]),
                                                    wb, tr), tags=(str(r["id"]),))
            self.log("[OK] 运行记录已刷新（%d 条）" % len(res))

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["runs"] = done
        self.async_run("runs", job, lambda r: None)

    def on_run_detail(self, _event):
        token = self._need_token()
        if not token:
            return
        sel = self.tree.selection()
        if not sel:
            return
        run_id = self.tree.item(sel[0], "tags")[0]

        def job():
            owner, repo = self._repo()
            wb = ghapi.job_result_json(token, owner, repo, run_id, "WorkBuddy")
            tr = ghapi.job_result_json(token, owner, repo, run_id, "Trae")
            return wb, tr

        def done(res):
            if isinstance(res, Exception):
                self.log("[详情获取失败] %s" % res)
                return
            wb, tr = res
            self.txt_checkin.delete("1.0", "end")
            self.txt_checkin.insert("end", "Run %s 明细:\n\nWorkBuddy: %s\n\nTraeWork: %s\n"
                                    % (run_id, json.dumps(wb, ensure_ascii=False) if wb else "无",
                                       json.dumps(tr, ensure_ascii=False) if tr else "无"))

        self._callbacks = getattr(self, "_callbacks", {})
        self._callbacks["detail"] = done
        self.async_run("detail", job, lambda r: None)


if __name__ == "__main__":
    App().mainloop()
