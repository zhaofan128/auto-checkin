# auto-checkin

每天自动签到：WorkBuddy「Buddy 加油站」签到 + 派 Buddy 旅行、TraeWork CN 签到领积分。
跑在 GitHub Actions 的服务器上，**电脑和手机全关机也会准时执行**。

## 执行时间

`.github/workflows/checkin.yml` 的 cron 用 UTC，对应北京时间：

| UTC | 北京时间 | 说明 |
|---|---|---|
| 22:20 | 06:20 | TraeWork 与 WorkBuddy 首次执行 |
| 01:10 | 09:10 | 补跑（幂等，已签到会跳过） |
| 05:30 | 13:30 | 补跑（幂等，已签到会跳过） |

GitHub 的定时任务高峰期可能延迟几分钟到几十分钟，属正常。签到接口是幂等的，重复执行不会重复领分。

想立即跑一次：Actions 页 → daily-checkin → Run workflow。

## 需要配置的 Secrets

Settings → Secrets and variables → Actions → New repository secret：

| Secret | 内容 |
|---|---|
| `WB_RT` | WorkBuddy 长效令牌（refresh token），纯字符串 |
| `TRAE_CREDS` | TraeWork 凭据，一段 JSON：`{"refresh_token":"...","device_id":"...","machine_id":"...","uid":"...","device_key_pem":"...","device_pub_pem":"..."}` |

凭据都不在仓库文件里，脚本从环境变量读取。

## 注意

- 仓库必须是 **Private**。
- GitHub 会自动停用「60 天无任何提交」的仓库里的定时任务。本仓库每天会跑 Actions，不算 inactivity 吗？——**算的**：Actions 运行不产生提交。仓库若 60 天没有 commit，定时任务会被自动停用。解法：每月随手推一次提交，或在 Actions 页手动点一次 Run workflow。
- Workflow 失败会在 GitHub 的通知里出现（Actions 失败默认发邮件）。

## 凭据过期后怎么修

- WorkBuddy 长效令牌约 30 天到期：在已登录 WorkBuddy 客户端的电脑上执行
  `python %USERPROFILE%\.workbuddy\scripts\rt_auth.py --export-rt`，把新令牌更新到 `WB_RT`。
- TraeWork refresh token 有效期到 2027-04-19 前后：在已登录 TraeWork 的电脑上执行
  `python %USERPROFILE%\.workbuddy\scripts\build_gh_secrets.py`，把生成的 JSON 更新到 `TRAE_CREDS`。
