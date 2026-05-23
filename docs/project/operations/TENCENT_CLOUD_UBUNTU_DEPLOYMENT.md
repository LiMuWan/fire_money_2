# FireMoney 腾讯云 Ubuntu 部署手册

这份文档用于把 FireMoney 部署到腾讯云轻量应用服务器，并让两个服务稳定常驻：

- `firemoney-preview.service`：预览页服务器，默认端口 `8765`
- `firemoney-beta-watch.service`：模拟盘 Beta 值守循环，负责早评、盘中 watch、晚评和调度审计

当前部署目标：

- 系统：Ubuntu Server 24.04 LTS
- 推荐目录：`/opt/firemoney`
- 推荐用户：`ubuntu`
- 密钥文件：本机 `~/.ssh/firemoney_tencent`
- 服务配置：`/etc/firemoney/firemoney.env`
- 运行数据：`/opt/firemoney/.firemoney/`

如果你只想看最短勾选版，先看这里：

- [一页部署清单](D:/workspace/FireMoney/docs/project/operations/TENCENT_CLOUD_UBUNTU_DEPLOYMENT_CHECKLIST.md)

## 快速路线

优先推荐用 GitHub 分支部署，因为代码已经推到远程仓库：

```text
https://github.com/LiMuWan/fire_money_2.git
```

当前可部署分支：

```text
codex/one-to-two-core-prune
```

最快路径是：

1. 腾讯云控制台重置服务器密码，并绑定 SSH 密钥。
2. 安全组放行 `22/tcp`，如果要公网看页面再放行 `8765/tcp` 给你的固定 IP。
3. SSH 登录服务器。
4. 从 GitHub 拉取 `codex/one-to-two-core-prune` 到 `/opt/firemoney`。
5. 执行 `sudo bash scripts/linux/install_firemoney_systemd.sh` 安装服务。
6. 配置 `/etc/firemoney/firemoney.env` 里的飞书密钥。
7. 启动 `firemoney-preview`，确认页面能打开。
8. 跑 `doctor`、`beta-check`、`feishu-test`。
9. 飞书测试通过后，再启动 `firemoney-beta-watch`。
10. 用 `bash scripts/linux/check_firemoney_server.sh` 验收。

如果你想“尽量少操作”，可以直接在 Windows 跑一键脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_tencent_ubuntu_one_click.ps1
```

这条命令默认会使用：

```text
IP: 81.70.202.132
用户: ubuntu
密钥: %USERPROFILE%\.ssh\firemoney_tencent
```

默认还会顺手做三件事：

- 启动 `firemoney-preview`
- 跑一次 `beta-check`
- 如果前两步通过，再启动 `firemoney-beta-watch`

如果你只想先把服务跑起来，按下面这段命令执行即可。把 `<你的服务器公网IP>` 替换成腾讯云公网 IP：

```powershell
ssh -i $env:USERPROFILE\.ssh\firemoney_tencent ubuntu@<你的服务器公网IP>
```

登录服务器后执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl rsync
sudo mkdir -p /opt/firemoney
sudo chown ubuntu:ubuntu /opt/firemoney

git clone -b codex/one-to-two-core-prune https://github.com/LiMuWan/fire_money_2.git /opt/firemoney
cd /opt/firemoney
sudo bash scripts/linux/install_firemoney_systemd.sh

sudo systemctl start firemoney-preview
sudo systemctl status firemoney-preview --no-pager
curl -fsS http://127.0.0.1:8765/core_workflow.html | grep FireMoney
```

到这里，预览服务应该已经起来。接下来不要急着开值守，先配置飞书：

```bash
sudo nano /etc/firemoney/firemoney.env
```

至少确认：

```text
FEISHU_ENABLED=true
```

然后填入 webhook 或 app 机器人配置。配置完成后：

```bash
sudo systemctl restart firemoney-preview

cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli doctor --brief --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli feishu-test
```

如果安装时提示 `python3.12-venv` 或 `ensurepip` 不可用，先补系统包：

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
sudo bash scripts/linux/install_firemoney_systemd.sh
```

确认飞书群收到测试消息后，再启动真实模拟盘值守：

```bash
sudo systemctl start firemoney-beta-watch
sudo systemctl status firemoney-beta-watch --no-pager

cd /opt/firemoney
bash scripts/linux/check_firemoney_server.sh
```

验收通过后，服务会开机自启；交易日只在应该发送早评、买入/卖出、晚评的时候发飞书，非交易日不发。

## 0. 先处理安全

你之前把服务器默认密码发到聊天里了，这个密码必须视为已经泄露。部署前先做这几件事：

1. 在腾讯云控制台重置实例密码。
2. 绑定 SSH 密钥，后续只用密钥登录。
3. 安全组只放行你的固定 IP：
   - `22/tcp`：SSH 登录
   - `8765/tcp`：如果需要公网看预览页，先只放行你的固定 IP
4. 不要把服务器密码、飞书 webhook、app secret 写入 Git 仓库。

如果你只是自己看页面，更推荐不开公网 `8765`，而是用 SSH 隧道：

```powershell
ssh -i $env:USERPROFILE\.ssh\firemoney_tencent -L 8765:127.0.0.1:8765 ubuntu@<你的服务器公网IP>
```

然后本机浏览器打开：

```text
http://127.0.0.1:8765/core_workflow.html
```

## 1. 本机生成 SSH 密钥

在 Windows PowerShell 执行：

```powershell
ssh-keygen -t ed25519 -C "firemoney-tencent" -f $env:USERPROFILE\.ssh\firemoney_tencent
Get-Content $env:USERPROFILE\.ssh\firemoney_tencent.pub
```

把输出的 `.pub` 公钥添加到腾讯云实例的 SSH 密钥，或追加到服务器：

```bash
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

测试密钥登录：

```powershell
ssh -i $env:USERPROFILE\.ssh\firemoney_tencent ubuntu@<你的服务器公网IP>
```

能登录后，再继续后面的部署。

## 2. 推荐方式：从 Windows 一键上传和安装

仓库已提供部署脚本：

```text
scripts/deploy_tencent_ubuntu.ps1
```

它只接受 SSH 私钥，不接受密码参数，避免密码进入命令历史。

在本机 `D:\workspace\FireMoney` 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_tencent_ubuntu.ps1 `
  -HostName <你的服务器公网IP> `
  -User ubuntu `
  -KeyPath $env:USERPROFILE\.ssh\firemoney_tencent `
  -StartPreview
```

这一步会自动完成：

- 打包当前代码，排除 `.git`、`.firemoney`、`.venv`、缓存和构建目录
- 上传到 `/opt/firemoney`
- 安装 Python venv 和 `requirements.txt`
- 安装并启用 systemd 服务
- 启动 `firemoney-preview`
- 运行服务器健康检查

第一次先不要加 `-StartBetaWatch`，因为飞书密钥还没配置好。

## 3. 手动方式：在服务器上安装

如果不用 Windows 部署脚本，可以 SSH 到服务器后手动执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl rsync
sudo mkdir -p /opt/firemoney
sudo chown ubuntu:ubuntu /opt/firemoney
```

上传代码有两种选择。

如果仓库可拉取：

```bash
git clone <你的仓库地址> /opt/firemoney
cd /opt/firemoney
```

如果仓库不方便公开，就从 Windows 上传：

```powershell
tar.exe -czf $env:TEMP\firemoney-deploy.tar.gz --exclude=.git --exclude=.firemoney --exclude=.venv --exclude=__pycache__ .
scp -i $env:USERPROFILE\.ssh\firemoney_tencent $env:TEMP\firemoney-deploy.tar.gz ubuntu@<你的服务器公网IP>:/tmp/firemoney-deploy.tar.gz
ssh -i $env:USERPROFILE\.ssh\firemoney_tencent ubuntu@<你的服务器公网IP> "tar -xzf /tmp/firemoney-deploy.tar.gz -C /opt/firemoney"
```

安装 systemd：

```bash
cd /opt/firemoney
sudo bash scripts/linux/install_firemoney_systemd.sh
```

## 4. 配置飞书和运行参数

编辑服务器环境变量：

```bash
sudo nano /etc/firemoney/firemoney.env
```

最小推荐配置：

```text
FIREMONEY_APP_DIR=/opt/firemoney
FIREMONEY_PYTHON=/opt/firemoney/.venv/bin/python
FIREMONEY_PREVIEW_BIND=127.0.0.1
FIREMONEY_PREVIEW_PORT=8765
FIREMONEY_BETA_INTERVAL_SECONDS=60
FIREMONEY_MARKET_DATA_TIMEOUT_SECONDS=20
FIREMONEY_ALLOW_MARKET_DATA_TIMEOUT=true
FEISHU_ENABLED=true
```

如果用群机器人 webhook：

```text
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_WEBHOOK_SECRET=
```

如果用应用机器人：

```text
FEISHU_APP_ID=cli_...
FEISHU_APP_SECRET=...
FEISHU_RECEIVE_ID=oc_...
FEISHU_RECEIVE_ID_TYPE=chat_id
```

保存后重启预览服务：

```bash
sudo systemctl restart firemoney-preview
```

如果你确实要公网访问 `8765`，把 `FIREMONEY_PREVIEW_BIND` 改成：

```text
FIREMONEY_PREVIEW_BIND=0.0.0.0
```

但安全组必须限制来源 IP。不要把没有鉴权的预览页直接暴露给全网。

## 5. 启动预览页

```bash
sudo systemctl start firemoney-preview
sudo systemctl status firemoney-preview --no-pager
```

服务器本机检查：

```bash
curl -fsS http://127.0.0.1:8765/core_workflow.html | grep FireMoney
```

如果你配置了公网 `8765`，本机浏览器打开：

```text
http://<你的服务器公网IP>:8765/core_workflow.html
```

如果你使用 SSH 隧道，本机浏览器打开：

```text
http://127.0.0.1:8765/core_workflow.html
```

## 6. 启动 Beta 值守前的预检

先跑 doctor：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli doctor --brief --market-data-timeout-seconds 20
```

再跑 beta-check：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20
```

再测试飞书：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli feishu-test --trade-date 2026-05-22
```

只有确认飞书收到测试消息后，再启动值守。

## 7. 启动 Beta 值守

```bash
sudo systemctl start firemoney-beta-watch
sudo systemctl status firemoney-beta-watch --no-pager
```

设置为开机自启已经由安装脚本完成，可确认：

```bash
systemctl is-enabled firemoney-preview
systemctl is-enabled firemoney-beta-watch
```

两个服务都应该返回：

```text
enabled
```

## 8. 一键健康检查

仓库提供了服务器健康脚本：

```bash
cd /opt/firemoney
bash scripts/linux/check_firemoney_server.sh
```

重点看这些：

- `firemoney-preview.service` 是否 active
- `firemoney-beta-watch.service` 是否 active
- `ss` 是否只有一个 `8765` 监听
- `preview_http_ok` 是否出现
- `schedule-health` 是否 ready 或非交易日正常 closed

单独检查端口：

```bash
ss -ltnp 'sport = :8765'
```

单独检查进程：

```bash
pgrep -af 'firemoney_preview_server|beta-start|one_to_two_cli'
```

## 8.1 首次部署验收表

首次部署完成后，逐项打勾：

```text
[ ] 已重置腾讯云默认密码
[ ] 已绑定 SSH 密钥，确认可以用密钥登录
[ ] 安全组只对你的固定 IP 放行 22/tcp
[ ] 如需公网预览，8765/tcp 只对你的固定 IP 放行
[ ] /opt/firemoney 已存在，并且是 codex/one-to-two-core-prune 分支
[ ] /etc/firemoney/firemoney.env 已创建，权限为 600
[ ] FEISHU_ENABLED=true
[ ] webhook 或 app 机器人配置已填入 env 文件
[ ] firemoney-preview.service 为 active
[ ] curl http://127.0.0.1:8765/core_workflow.html 能看到 FireMoney
[ ] doctor --brief 不是 blocked
[ ] beta-check 能跑通
[ ] feishu-test 群里能收到
[ ] firemoney-beta-watch.service 为 active
[ ] schedule-health --brief 能输出 ready / 非交易日 closed
[ ] notifications --action-only 能看到飞书 sent 记录
[ ] paper-db --brief 能读取模拟盘账本
```

对应命令：

```bash
cd /opt/firemoney
git branch --show-current
git log --oneline --max-count=3
sudo stat -c "%a %U:%G %n" /etc/firemoney/firemoney.env
systemctl is-active firemoney-preview
systemctl is-active firemoney-beta-watch
curl -fsS http://127.0.0.1:8765/core_workflow.html | grep FireMoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli doctor --brief --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20
bash scripts/linux/check_firemoney_server.sh
```

## 9. 日常运维命令

查看预览日志：

```bash
journalctl -u firemoney-preview -n 100 --no-pager
tail -n 100 /opt/firemoney/.firemoney/logs/firemoney_preview.log
```

查看值守日志：

```bash
journalctl -u firemoney-beta-watch -n 100 --no-pager
tail -n 100 /opt/firemoney/.firemoney/logs/firemoney_beta_watch.log
```

看今天调度是否漏发：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
```

看飞书记录：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20
```

看模拟盘账本：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20
```

看回测证据：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-backtest --start-date 2020-01-01 --end-date 2026-05-23 --brief
```

## 10. 更新代码

如果服务器代码来自 Git：

```bash
cd /opt/firemoney
git fetch origin
git checkout codex/one-to-two-core-prune
git pull --ff-only origin codex/one-to-two-core-prune
/opt/firemoney/.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart firemoney-preview
sudo systemctl restart firemoney-beta-watch
bash scripts/linux/check_firemoney_server.sh
```

如果你以后把代码合并到 `main`，再把上面的分支名改成：

```bash
git checkout main
git pull --ff-only origin main
```

如果用 Windows 部署脚本，重新执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_tencent_ubuntu.ps1 `
  -HostName <你的服务器公网IP> `
  -User ubuntu `
  -KeyPath $env:USERPROFILE\.ssh\firemoney_tencent `
  -StartPreview `
  -RunBetaCheck
```

确认 `beta-check` 通过后，再重启值守：

```powershell
ssh -i $env:USERPROFILE\.ssh\firemoney_tencent ubuntu@<你的服务器公网IP> "sudo systemctl restart firemoney-beta-watch && sudo systemctl status firemoney-beta-watch --no-pager"
```

## 11. 常见故障

### 网页打不开

```bash
sudo systemctl status firemoney-preview --no-pager
journalctl -u firemoney-preview -n 100 --no-pager
ss -ltnp 'sport = :8765'
curl -fsS http://127.0.0.1:8765/core_workflow.html | head
```

如果服务器本机 `curl` 正常，但公网打不开，通常是安全组或 `FIREMONEY_PREVIEW_BIND` 问题。

### 早评或晚评没发

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20
journalctl -u firemoney-beta-watch -n 200 --no-pager
```

如果是非交易日，不发早评/晚评是正确行为。

### 每天都是防守空仓日

先区分两种情况：

- 行情源不可用：这是系统保护，禁止模拟买入。
- 行情源可用但候选不达标：这是策略风控，继续空仓。

排查：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli doctor --brief --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli morning --brief --market-data-timeout-seconds 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-decision --brief
```

### 飞书没收到

```bash
sudo cat /etc/firemoney/firemoney.env
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli feishu-test
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --brief --limit 10
```

确认：

- `FEISHU_ENABLED=true`
- webhook 或 app 机器人配置完整
- 群机器人没有被群设置拦截
- 服务器可以访问飞书 API

### 出现多个实例

服务脚本使用 `flock` 做单实例保护。仍然可以检查：

```bash
pgrep -af 'beta-start|firemoney_preview_server|one_to_two_cli'
ss -ltnp 'sport = :8765'
```

如果确实有历史残留进程：

```bash
sudo systemctl restart firemoney-preview
sudo systemctl restart firemoney-beta-watch
```

不要手动乱杀不认识的系统进程。

## 12. 上线前验收标准

内部自用 Beta 可以先跑，但对外商用前至少要满足：

- 服务器连续 30 个交易日 `schedule-health` 无阻断
- 早评、真实模拟买入、真实模拟卖出、晚评都有可审计 `sent` 记录
- 真实模拟盘至少 30 笔闭环交易
- 真实模拟盘胜率、收益、赚撤比和最大回撤达标
- 2020 起逐年回测仍保持无亏损年份或弱年份可解释
- 腾讯云服务能开机自启，异常退出后自动恢复
- 飞书密钥、服务器密钥、账本数据都不进入 Git
- 不对外宣传“保证盈利”，只做风险揭示充分的研究和模拟盘辅助

## 13. 建议的日常节奏

交易日前一天或当天盘前：

```bash
cd /opt/firemoney
bash scripts/linux/check_firemoney_server.sh
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
```

收盘后：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli missed-opportunities --start-date 2026-05-01 --end-date 2026-05-23 --brief
```

每周复盘：

```bash
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-backtest --start-date 2020-01-01 --end-date 2026-05-23 --brief
```

核心原则：服务器稳定只是第一步，真正决定能不能上线的是“不断档值守 + 真实模拟盘闭环 + 回撤受控 + 合规边界清楚”。
