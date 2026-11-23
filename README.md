# auto-checkin

统一的 AI 站点自动签到项目。本仓库是合并后的宿主仓库：

- 原 `auto-checkin`：WorkBuddy、TraeWork CN、Qoder CN、Qoder Global、MiniMax Code、LobsterAI
- 原 `kk-auto-checkin`：KK、DGB、AIAIAI、帮帮程序员、可萌、SeekAI、BENST

合并后共用一套 Python core、账户注册表、日志规范和平台适配器。最终目标是单一项目根、单一主入口、单一调度；当前迁移状态见下文“迁移状态”。

## 当前状态

| 指标 | 值 |
|---|---|
| 账户目标 | 13 |
| 平台适配器 | 12（Qoder 一个模块，CN/Global 两个账户） |
| 已验证（verified） | 11 |
| 受 Secret 阻塞（blocked_no_secret） | 2：Qoder CN/Global（账号资格/桌面设备身份） |
| 测试 | 100 通过 |
| 运行时 | Python 3.12 |
| 旧 kk 仓库 | 定时任务已停用，仓库保留待归档 |

- KK 的 Playwright 浏览器 fallback 已在 GitHub Actions 中真实通过 Turnstile：`solved`，2 次点击，无需人工 token。
- SeekAI 在更新 `SEEKAI_TOKEN` 后，同一浏览器 fallback 也真实通过：`solved`，2 次点击，无需人工 Turnstile token。
- Qoder CN/Global 的 usage 已修复（1433 / 771），但 campaigns 只有 `VIEW_DETAILS`，没有 `CLAIM_BENEFIT`。
- Qoder CN 的 PAT 可正常换取 job token，但账户类型是 `personal_standard`；官方每日 100 Credits 仅对 Pro 试用/个人付费开放，因此当前账号不满足资格。
- Qoder Global 仍需桌面设备身份并确认账号资格。
- `SEEKAI_TURNSTILE_TOKEN` / `KK_TURNSTILE_TOKEN` 只是可选应急覆盖，不是默认必需。
- 旧 kk 仓库的定时任务已停用；仓库保留用于回滚，主 workflow 跑完一个自然周期后归档。

完整逐行状态与真实脱敏事件：

- [docs/platform-matrix.md](docs/platform-matrix.md)
- [docs/verified-probes.md](docs/verified-probes.md)

## 架构

```text
src/
├─ core/                 # 配置、Secret、状态、锁、刷新、日志、积分、HTTP、重试、限流
├─ browser/              # Turnstile 检测/降级策略
├─ config/
│  ├─ settings.py
│  └─ registry.py        # 12 个适配器 / 13 个账户目标
└─ platforms/
   ├─ base.py            # AccountAdapter / PlatformAdapter 接口
   ├─ workbuddy/
   ├─ traework/          # 含 P-256 设备签名 crypto.py
   ├─ qoder/             # CN / Global 独立账户
   ├─ minimax/
   ├─ lobsterai/
   ├─ kk/
   └─ newapi/            # 共享 New-API 基类 + 6 个站点
      └─ sites/
         ├─ dgb.py
         ├─ aiaiai.py
         ├─ helpcoder.py
         ├─ kemeng.py
         ├─ seekai.py
         └─ benst.py
```

每个适配器负责：

- 登录态读取
- 签到
- 积分字段解析
- 账户标识
- 错误类型与降级

## 账户与验证状态

以 2026-11-23 的真实探测结果为准；余额会变化，具体以最新日志为准。

| 账户目标 | 状态 | points_gained | points_current | points_source |
|---|---|---:|---:|---|
| WorkBuddy | verified | 100 | 3500 | api_field |
| TraeWork CN | verified | null | 100 | api_unavailable |
| Qoder CN | blocked_no_secret | null | 1433 | api_field |
| Qoder Global | blocked_no_secret | null | 771 | api_field |
| MiniMax Code | verified | 400 | null | api_unavailable |
| LobsterAI | verified | 100 | null | api_unavailable |
| DGB | verified | null | 112238913 | api_unavailable |
| AIAIAI | verified | null | 38636 | api_unavailable |
| 帮帮程序员 | verified | null | 160000000 | api_unavailable |
| 可萌 | verified | null | 1008044 | api_unavailable |
| BENST | verified | null | 773199 | api_unavailable |
| SeekAI | verified | null | 18999999 | api_unavailable |
| KK | verified | null | 997759 | api_unavailable |

说明：

- DGB/AIAIAI/帮帮程序员/可萌/BENST/SeekAI/KK 当天均为 `already_checked`，所以 `points_gained=null`，当前余额来自真实接口。
- 拿不到当前总额时写 `null`，没有用 0 或猜测值。
- New-API 的 `total_quota` 是累计值，禁止当作当前余额；当前余额优先取 `/api/user/self`、`/api/data/self`，再尝试 `/api/usage/token/`。

## 快速开始

要求 Python 3.12。浏览器 fallback 需要 Playwright 和 Chromium：

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

python3 -m pytest tests -q
python3 -m compileall -q src tests tools

# 统一入口
python3 -m src.main --profile manual --platform workbuddy --dry-run
```

### 运行单平台探针

```bash
# dry-run：只查状态/积分，不执行签到
python3 tools/probe_platform.py --platform workbuddy

# 真正签到
python3 tools/probe_platform.py --platform workbuddy --apply
```

`--platform` 可选值：

```text
workbuddy
traework
qoder_cn
qoder_global
minimax
lobsterai
kk
dgb
aiaiai
helpcoder
kemeng
seekai
benst
```

探针默认写入 `.probe/`，不会修改宿主 `history/run.log`。

### GitHub Actions 探针

`.github/workflows/probe.yml` 提供手动入口：

- Actions → `probe-platform` → Run workflow
- 选择平台、是否 `apply`
- 输出为脱敏后的 JSON 事件，不含 Token/Cookie

## Secrets

所有 Secret 只通过环境变量/Secrets 读取，仓库中没有明文。

### 自动签到所需

```text
WB_RT
TRAE_CREDS
QODER_CN_TOKEN
QODER_GLOBAL_TOKEN
MM_CREDS
LOBSTER_CREDS
KK_TOKEN
CHECKIN_USERNAME
CHECKIN_PASSWORD
SEEKAI_TOKEN
BENST_TOKEN
GH_PAT
```

- `GH_PAT` 需要可写 Secrets，用于 WorkBuddy/TraeWork/Qoder CN/MiniMax/LobsterAI 的滚动令牌写回。
- 没有 `GH_PAT` 写权限时，滚动账户返回 `skipped`，`skipped_reason=secret_writeback_unavailable`。
- SeekAI 账号通过 GitHub 注册，签到使用 `SEEKAI_TOKEN`，不参与 `CHECKIN_USERNAME` / `CHECKIN_PASSWORD` 回退；浏览器 fallback 负责 Turnstile。
- `SEEKAI_TOKEN` 在当前真实代码里是静态访问令牌，没有可调用的 refresh 接口；当前宿主令牌已更新并验证。
- `KK_TOKEN` 可长期使用；KK 的 Turnstile 由浏览器 fallback 自动处理。

### Qoder 桌面设备身份

Qoder 每日积分只对带有官方桌面设备身份的 campaigns 请求返回
`CLAIM_BENEFIT`。可选 Secret：

```text
QODER_CN_MACHINE_TOKEN
QODER_CN_MACHINE_TYPE
QODER_GLOBAL_MACHINE_TOKEN
QODER_GLOBAL_MACHINE_TYPE
```

没有这些值时，usage 仍可读取，但 campaigns 只返回 `VIEW_DETAILS`，签到保持
`blocked`，不会伪造成功。即使设备身份齐全，Qoder CN 的
`personal_standard` 账号仍不满足 Pro 试用/付费活动资格。

### Turnstile 人工 token（可选应急）

```text
KK_TURNSTILE_TOKEN
SEEKAI_TURNSTILE_TOKEN
```

这两个 token 不再作为默认路径。默认使用 Playwright 浏览器 fallback；人工 token 只在浏览器连续失败时临时覆盖。浏览器也失败时：

- KK：`failed` + `turnstile_timeout` 或 `browser_unavailable`
- SeekAI：`failed` + `turnstile_timeout` 或 `browser_unavailable`

### 四个密码站点的逐站覆盖（可选）

```text
CHECKIN_USERNAME_DGB / CHECKIN_PASSWORD_DGB
CHECKIN_USERNAME_AIAIAI / CHECKIN_PASSWORD_AIAIAI
CHECKIN_USERNAME_HELPCODER / CHECKIN_PASSWORD_HELPCODER
CHECKIN_USERNAME_KEMENG / CHECKIN_PASSWORD_KEMENG
```

未配置时回退到 `CHECKIN_USERNAME` / `CHECKIN_PASSWORD`。

### 键名兼容

新统一别名优先，旧键名回退；旧键名不会被删除或强制改名。完整规则见：

- [docs/secret-compatibility.md](docs/secret-compatibility.md)

## 日志与状态

- `history/events.jsonl`：结构化事件，唯一事实来源，纯追加。
- `history/run.log`：人类可读摘要，纯追加。
- `history/archive/kk-auto-checkin/run.log`：旧 kk 历史日志归档。
- 新 core 写入不截断；旧 workflow 的 `tail -n 120 + mv` 已移除，改为纯追加。
- 旧 kk 历史日志已归档到 `history/archive/kk-auto-checkin/`，含 SHA-256 `META.json`。
- 状态按账户独立保存，写入使用临时文件 + `os.replace`，并加账户级文件锁。
- Qoder CN/Global 使用两个独立状态文件、两把锁、两个 `platform` 日志值。
- 日志不记录 Token/Cookie/密码；账号只保留脱敏值。

锁的适用边界：

- `flock` 只保护同一 runner/本机进程。
- 不能跨 GitHub Actions step/job 传递。
- 跨 job 只能靠单 job + `concurrency.group` 串行。

详见 [docs/refresh-locking.md](docs/refresh-locking.md)。

## 调度

`.github/workflows/checkin.yml` 现在是唯一主 workflow，单 job 调用 `python -m src.main`。

| UTC | 北京时间 | profile | 范围 |
|---|---|---|---|
| 18:02 / 18:12 | 02:02 / 02:12 | `quota` | BENST |
| 22:20 | 06:20 | `morning` | 全量 |
| 01:10 | 09:10 | `midmorning` | 全量 |
| 02:15 | 10:15 | `qoder` | Qoder CN/Global |
| 05:30 | 13:30 | `afternoon` | 全量 |

- `concurrency.group: daily-checkin`，不并发。
- 每次运行提交 `history/run.log`、`history/events.jsonl`、`state/`。
- 旧 kk 仓库 workflow 已手动停用，仓库保留待归档。
- `probe-platform` 仍可手动探测任意平台。

## 迁移状态

已完成：

- 13 个账户目标适配器
- 统一 core：Secret 兼容、状态、锁、刷新单飞、日志、积分、脱敏、重试、限流
- 100 个测试
- 11 个账户目标真实签到验证；Qoder CN/Global 已拿到 usage，但 Qoder CN 账号资格不符、Global 缺设备身份
- `src/main.py` 单主入口
- 主 workflow 已切换为单 job，完整跑通 13 个账户目标
- 旧 kk 历史日志归档与 SHA-256 `META.json`
- 旧 workflow 日志截断逻辑移除，改为纯追加
- 旧 kk 定时任务已停用

待完成：

- Qoder 活动资格：CN 需要 Pro 试用/付费账号；Global 还需要桌面设备身份
- 主 workflow 跑完一个自然周期后归档旧 kk 仓库

## 开发

新增平台适配器时：

1. 在 `src/platforms/<platform>/` 实现 `AccountAdapter`。
2. 在 `src/config/registry.py` 注册 `AccountSpec`。
3. 在 `docs/platform-matrix.md` 增加行。
4. 至少补一个成功/降级单元测试。
5. 跑全量测试和 `probe_platform.py`。

## 安全

- 不要把 Token、Cookie、密码写入代码、日志、Issue 或提交。
- 如果 Token 曾出现在公开对话/截图中，请立即轮换。
- 轮换 `GH_PAT` 后，同步更新宿主仓库 Secret，否则滚动写回会失败。
- 仅用于个人自动化，请遵守各平台用户协议。

MIT License。
