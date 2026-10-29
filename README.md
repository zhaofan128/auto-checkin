# auto-checkin · 每天自动签到（跑在 GitHub 云端）

用 GitHub Actions 每天定时给 **WorkBuddy**（签到领积分 + 派 Buddy 旅行）和 **TraeWork CN**（签到领积分）打卡。

**你不需要开着电脑，也不需要开着手机** —— 一切跑在 GitHub 的服务器上。

## 🖥 桌面版（不想碰命令行？）

到 [Releases](https://github.com/zhaofan128/auto-checkin/releases) 下载 `AutoCheckin.exe`（绿色单文件，无需安装 Python）：

液态玻璃界面 · 果冻开关 · **一键开启**：

1. 双击运行，自动识别本机已保存的 GitHub Token（无需手动输入）
2. 点「🚀 一键开启」—— 提取本机凭据、写入 Secrets、开启自动轮换，一次搞定
3. 仪表盘随时看两个平台的余额 / 今日签到 / 猫猫旅行状态
4. 果冻开关独立控制 WorkBuddy / TraeWork 的云端自动签到启停
5. 「💻 立即签到」本机直签（幂等，顺带给令牌续期）

> Token 保存在本机 `%APPDATA%\AutoCheckin\config.json`，不上传到任何第三方。
> 需要 Windows 10+ 且已安装 Edge WebView2 运行时（绝大多数系统自带）。
> 源码在 [app/](app/) 目录，可用 `pyinstaller` 自行打包。

## ✨ 特性

- **设备全离线**：作业在 GitHub 的 runner 上执行，跟你本机、客户端是否运行完全无关。
- **令牌永不过期**（重点）：WorkBuddy 的长效令牌名义上只有 30 天，但服务端**每次刷新都会下发一个新令牌**。本仓库在每次签到后自动把新令牌写回 Secret，形成滚动续期——只要定时任务还在跑，就一直有效。TraeWork 同理（它的令牌约半年，同样会滚动）。
- **一天三次，幂等**：06:20 / 09:10 / 13:30（北京时间）各跑一次，签过就跳过，不会重复领；一次失败后面还有两次补。
- **凭据零明文**：脚本只从环境变量读取，仓库里没有任何密钥。
- **自动保活**：GitHub 会停用「60 天无提交」仓库的定时任务，本项目每天第一次运行会自动提交一条记录（`history/run.log`），避免被停用。

## 🚀 三步上手

### 1. Fork 本仓库（点右上角 Fork）

### 2. 在本机取凭据

在**已登录 WorkBuddy 和 TraeWork 桌面端的电脑上**运行：

```bash
git clone <你的仓库地址> && cd auto-checkin
python tools/get_creds.py
```

脚本会打印两段内容：

- `WB_RT` —— 一长串 JWT
- `TRAE_CREDS` —— 一段 JSON

> 脚本纯标准库，只读取本机客户端的登录态文件，不上传任何数据。支持 Windows / macOS。

### 3. 填进 GitHub Secrets

Settings → Secrets and variables → Actions → **New repository secret**，建三个：

| Secret | 内容 | 用途 |
|---|---|---|
| `WB_RT` | 上一步打印的长串 JWT | WorkBuddy 长效令牌 |
| `TRAE_CREDS` | 上一步打印的 JSON | TraeWork 凭据（刷新令牌 + 设备密钥） |
| `GH_PAT` *可选* | 一个能写 Secrets 的 GitHub 令牌（勾选 `repo`） | 用于自动写回轮换后的新令牌 |

> 不填 `GH_PAT` 也能正常签到，只是令牌不会自动轮换，WorkBuddy 那条约 30 天后需要手动更新一次。

### 4. 验证

Actions 页 → **daily-checkin** → **Run workflow**（手动跑一次）。两个 job 全绿即可，之后就不用管了。

## ⏰ 执行时间

cron 用 UTC，对应北京时间：

| UTC | 北京时间 |
|---|---|
| 22:20 | 06:20 |
| 01:10 | 09:10 |
| 05:30 | 13:30 |

GitHub 高峰期可能延迟几分钟到几十分钟，属正常。

## ❓ 常见问题

**TraeWork 桌面端被踢下线了？**
续期会生成新的会话，官方机制会让其他客户端重新登录。重新登录一次即可，不影响签到。

**某个 job 失败了？**
GitHub 会给仓库所有者发邮件。多数情况是令牌失效，重新跑一次 `tools/get_creds.py` 更新对应 Secret 即可。

**长期不用会停吗？**
不会。每天第一次运行会自动提交 `history/run.log`，仓库始终有活跃提交。

**只想签其中一个？**
删掉 `.github/workflows/checkin.yml` 里对应的 job 就行。

## ⚠️ 说明

- 本项目通过调用官方的公开 HTTP 接口完成签到，不登录网页、不模拟点击。
- 令牌等同账号钥匙：Secrets 是加密的，fork 后需要自己填；请妥善保管本机的 `tools/get_creds.py` 输出。
- 仅供个人自动化使用，请遵守对应平台的用户协议。

MIT License。
