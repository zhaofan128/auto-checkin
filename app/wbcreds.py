#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在本机生成 GitHub Actions 需要的两个 Secret 值（纯标准库，除了取令牌外不联网）。

用法（在已登录 WorkBuddy / TraeWork 桌面端的电脑上）：
    python tools/get_creds.py

输出：
    WB_RT       —— 粘贴到仓库 Secret  WB_RT
    TRAE_CREDS  —— 粘贴到仓库 Secret  TRAE_CREDS（一段 JSON）

只在本机运行，不会上传任何东西；生成的令牌等同账号钥匙，请勿外传。
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

# ---------------- TraeWork 本地登录态解密（AES-128-CBC，纯标准库实现） ----------------
SALT_A = bytes([82, 9, 106, 213, 48, 54, 165, 56, 191, 64, 163, 158, 129, 243, 215, 251,
                124, 227, 57, 130, 155, 47, 255, 135, 52, 142, 67, 68, 196, 222, 233, 203,
                84, 123, 148, 50, 166, 194, 35, 61, 238, 76, 149, 11, 66, 250, 195, 78, 8,
                46, 161, 102, 40, 217, 36, 178, 118, 91, 162, 73, 109, 139, 209, 37])
SALT_B = bytes([31, 221, 168, 51, 136, 7, 199, 49, 177, 18, 16, 89, 39, 128, 236, 95,
                96, 81, 127, 169, 25, 181, 74, 13, 45, 229, 122, 159, 147, 201, 156, 239,
                160, 224, 59, 77, 174, 42, 245, 176, 200, 235, 187, 60, 131, 83, 153, 97,
                23, 43, 4, 126, 186, 119, 214, 38, 225, 105, 20, 99, 85, 33, 12, 125])
SALT_AES = bytes(a ^ b for a, b in zip(SALT_A, SALT_B))
STORAGE_KEY = "iCubeAuthInfo://icube.cloudide"


def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _build_sbox():
    inv = [0] * 256
    for i in range(1, 256):
        for j in range(1, 256):
            if _gmul(i, j) == 1:
                inv[i] = j
                break
    sb = [0] * 256
    for i in range(256):
        x = inv[i] if i else 0
        s = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            s ^= x
        sb[i] = s ^ 0x63
    return sb


SBOX = _build_sbox()
INV = [0] * 256
for _i, _v in enumerate(SBOX):
    INV[_v] = _i
RC = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _expand(key):
    w = [list(key[i * 4:i * 4 + 4]) for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1][:]
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RC[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    return w


def _rk(w, r):
    ws = w[r * 4:r * 4 + 4]
    return [ws[c][k] for c in range(4) for k in range(4)]


def aes128_cbc_decrypt(key, iv, data):
    w = _expand(key)
    out = b""
    prev = list(iv)

    def addrk(s, k):
        return [s[i] ^ k[i] for i in range(16)]

    def isub(s):
        return [INV[b] for b in s]

    def ishift(s):
        return [s[0], s[13], s[10], s[7], s[4], s[1], s[14], s[11],
                s[8], s[5], s[2], s[15], s[12], s[9], s[6], s[3]]

    def imix(s):
        o = []
        for c in range(4):
            a = s[c * 4:c * 4 + 4]
            o += [_gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9),
                  _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13),
                  _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11),
                  _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)]
        return o

    for off in range(0, len(data), 16):
        blk = list(data[off:off + 16])
        s = addrk(blk, _rk(w, 10))
        for r in range(9, 0, -1):
            s = ishift(s)
            s = isub(s)
            s = addrk(s, _rk(w, r))
            s = imix(s)
        s = addrk(isub(ishift(s)), _rk(w, 0))
        out += bytes(a ^ b for a, b in zip(s, prev))
        prev = blk
    return out


def decrypt_storage_value(b64):
    buf = base64.b64decode(b64)
    rb, enc = buf[6:38], buf[38:]
    h = hashlib.sha512(rb).digest()
    fh = hashlib.sha512(h + SALT_AES).digest()
    pt = aes128_cbc_decrypt(fh[:16], fh[16:32], enc)[64:]
    pad = pt[-1] if pt else 0
    if 1 <= pad <= 16:
        return pt[:-pad]
    return pt.rstrip(b"\x00").rstrip()


def trae_creds():
    ad = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    for name in ("TRAE SOLO CN", "Trae CN", "TRAE SOLO", "Trae"):
        path = os.path.join(ad, name, "User", "globalStorage", "storage.json")
        if not os.path.isfile(path):
            continue
        try:
            st = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            continue
        enc = st.get(STORAGE_KEY)
        if not enc:
            continue
        try:
            raw = enc if enc.strip().startswith("{") else decrypt_storage_value(enc).decode("utf-8", "replace")
            auth = json.loads(raw)
        except Exception as e:
            print("[!] 解密 %s 失败: %s" % (name, e))
            continue
        dev_id, priv, pub, uid = "", "", "", ""
        for k in st:
            m = re.match(r"^iCubeAuthInfo://icube-dc:(\d+)$", k)
            if m:
                dev_id = m.group(1)
                try:
                    dv = json.loads(decrypt_storage_value(st[k]).decode("utf-8", "replace"))
                except Exception:
                    dv = json.loads(st[k]) if str(st[k]).strip().startswith("{") else {}
                priv = dv.get("privateKeyPEM", "")
                pub = dv.get("publicKeyPEM", "")
                uid = str(auth.get("userId") or m.group(1))
        rt_m = re.search(r'"refreshToken"\s*:\s*"([^"]+)"', raw)
        if not (rt_m and dev_id and priv and pub):
            continue
        return {
            "refresh_token": rt_m.group(1),
            "device_id": dev_id,
            "machine_id": st.get("telemetry.machineId") or "",
            "uid": uid,
            "device_key_pem": priv,
            "device_pub_pem": pub,
        }, name
    return None, None


def wb_refresh(rt):
    """用长效令牌换一个新的（同时把到期时间往后滚 30 天）。"""
    req = urllib.request.Request("https://copilot.tencent.com/v2/plugin/auth/token/refresh",
                                 data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Refresh-Token", rt)
    req.add_header("X-Auth-Refresh-Source", "plugin")
    req.add_header("X-Domain", "copilot.tencent.com")
    with urllib.request.urlopen(req, timeout=25) as r:
        res = json.loads(r.read().decode("utf-8", "replace"))
    if res.get("code") != 0:
        return None, res.get("msg")
    d = res.get("data") or {}
    return (d.get("refreshToken") or rt), None


def wb_rt():
    home = os.path.expanduser("~")
    for p in (os.path.join(home, ".workbuddy", "checkin-rt.json"),
              os.path.join(home, ".workbuddy", "rt.json")):
        if os.path.isfile(p):
            try:
                return json.load(io.open(p, encoding="utf-8")).get("rt") or ""
            except Exception:
                pass
    return ""


def main():
    print("=" * 68)
    print("WorkBuddy 长效令牌（WB_RT）")
    print("=" * 68)
    rt = wb_rt()
    if not rt:
        print("[!] 未找到 WorkBuddy 令牌文件 ~/.workbuddy/checkin-rt.json")
        print("    请先在 WorkBuddy 客户端登录，再用其签到助手导出一次长效令牌。")
    else:
        new_rt, err = wb_refresh(rt)
        if new_rt:
            print(new_rt)
            print("\n（上面这串就是 WB_RT 的值，已顺带刷新，到期时间顺延 30 天）")
        else:
            print("[!] 刷新失败: %s" % err)

    print()
    print("=" * 68)
    print("TraeWork 凭据（TRAE_CREDS）")
    print("=" * 68)
    creds, name = trae_creds()
    if not creds:
        print("[!] 未找到 TraeWork 登录态，请先启动 TraeWork 客户端并登录一次。")
    else:
        print(json.dumps(creds, ensure_ascii=False))
        print("\n（来自 %s；上面这串 JSON 就是 TRAE_CREDS 的值）" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
