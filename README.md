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
| 受 Secret 阻塞（blocked_no_secret） | 2：SeekAI、KK |
| 测试 | 95 通过 |
| 运行时 | Python 3.12 |
| 旧 kk 仓库 | 仍在运行，未归档 |

- WorkBuddy、TraeWork、Qoder CN/Global、MiniMax、LobsterAI、DGB、AIAIAI、帮帮程序员、可萌、BENST 已完成真实响应探测。
- SeekAI 和 KK 今天返回了真实 `already_checked` 与当前余额，但下一次未签到时会要求 Turnstile：
  - SeekAI 需要 `SEEKAI_TURNSTILE_TOKEN`
  - KK 需要 `KK_TURNSTILE_TOKEN`
- 缺少人工 Turnstile token 时，这两个账户返回 `skipped` + `turnstile_unavailable`，不会伪造成功。
- 旧 kk 仓库只作为新宿主验证完成前的临时兜底；13/13 验证完成后停用，不长期双跑。

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
| Qoder CN | verified | null | null | api_unavailable |
| Qoder Global | verified | null | null | api_unavailable |
| MiniMax Code | verified | 400 | null | api_unavailable |
| LobsterAI | verified | 100 | null | api_unavailable |
| DGB | verified | null | 112238913 | api_unavailable |
| AIAIAI | verified | null | 38636 | api_unavailable |
| 帮帮程序员 | verified | null | 160000000 | api_unavailable |
| 可萌 | verified | null | 1008044 | api_unavailable |
| BENST | verified | null | 773199 | api_unavailable |
| SeekAI | blocked_no_secret | null | 18999999 | api_unavailable |
| KK | blocked_no_secret | null | 997759 | api_unavailable |

说明：

- DGB/AIAIAI/帮帮程序员/可萌/BENST/SeekAI/KK 当天均为 `already_checked`，所以 `points_gained=null`，当前余额来自真实接口。
- 拿不到当前总额时写 `null`，没有用 0 或猜测值。
- New-API 的 `total_quota` 是累计值，禁止当作当前余额；当前余额优先取 `/api/user/self`、`/api/data/self`，再尝试 `/api/usage/token/`。

## 快速开始

要求 Python 3.12。

```bash
python3 -m pytest tests -q
python3 -m compileall -q src tests tools
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

### Turnstile 人工 token

```text
KK_TURNSTILE_TOKEN
SEEKAI_TURNSTILE_TOKEN
```

这两个 token 短期有效，无法从其他 Secret 推导。缺失时：

- KK：`skipped` + `turnstile_unavailable`
- SeekAI：`skipped` + `turnstile_unavailable`

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
- 新 core 写入不截断；旧 workflow 的日志收敛在主 workflow 替换时完成。
- 状态按账户独立保存，写入使用临时文件 + `os.replace`，并加账户级文件锁。
- Qoder CN/Global 使用两个独立状态文件、两把锁、两个 `platform` 日志值。
- 日志不记录 Token/Cookie/密码；账号只保留脱敏值。

锁的适用边界：

- `flock` 只保护同一 runner/本机进程。
- 不能跨 GitHub Actions step/job 传递。
- 跨 job 只能靠单 job + `concurrency.group` 串行。

详见 [docs/refresh-locking.md](docs/refresh-locking.md)。

## 调度

当前线上仍使用原有 `.github/workflows/checkin.yml`（5 个旧 job），新 core 通过 `probe-platform` 手动验证。主入口/主调度收敛是下一步工作；在完成前：

- 旧 kk 仓库定时任务不停。
- 旧 auto 仓库 workflow 继续作为在线兜底。
- 新宿主完成 13/13 验证后再替换。

新注册表已定义 profile：

- `quota`：BENST 02:00/02:10 配额窗口
- `qoder`：Qoder CN/Global
- `morning` / `midmorning` / `afternoon`：全量
- `manual`：手动探针

## 迁移状态

已完成：

- 13 个账户目标适配器
- 统一 core：Secret 兼容、状态、锁、刷新单飞、日志、积分、脱敏、重试、限流
- 95 个测试
- 11 个账户目标真实响应验证
- 旧 kk 历史日志归档路径与平台矩阵

待完成：

- `src/main.py` 单主入口与主 workflow 收敛
- 旧 workflow 的日志截断逻辑移除
- SeekAI / KK 的 Turnstile 人工 token 配置
- 13/13 验证后停用旧 kk 仓库

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
