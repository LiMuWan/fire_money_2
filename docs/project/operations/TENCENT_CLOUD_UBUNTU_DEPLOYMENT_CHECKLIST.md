# FireMoney 腾讯云部署一页清单

适合你现场照着勾选，不需要翻长文。

## 部署前

| 状态 | 动作 | 命令 / 结果 |
|---|---|---|
| [ ] | 重置腾讯云密码 | 控制台重置 |
| [ ] | 绑定 SSH 密钥 | `ssh-keygen` 生成后导入腾讯云 |
| [ ] | 放行 SSH | 安全组放行 `22/tcp` |
| [ ] | 预览页访问控制 | `8765/tcp` 只放行你的固定 IP，或只用 SSH 隧道 |
| [ ] | 检查本机私钥 | `%USERPROFILE%\.ssh\firemoney_tencent` |

## 一键部署

| 状态 | 动作 | 命令 / 结果 |
|---|---|---|
| [ ] | 执行一键部署 | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_tencent_ubuntu_one_click.ps1` |
| [ ] | 默认 IP | `81.70.202.132` |
| [ ] | 默认用户 | `ubuntu` |
| [ ] | 默认私钥 | `%USERPROFILE%\.ssh\firemoney_tencent` |
| [ ] | 默认分支 | `codex/one-to-two-core-prune` |

## 部署后检查

| 状态 | 动作 | 命令 / 结果 |
|---|---|---|
| [ ] | 预览服务启动 | `sudo systemctl status firemoney-preview --no-pager` |
| [ ] | 页面可访问 | `http://127.0.0.1:8765/core_workflow.html` |
| [ ] | doctor 通过 | `doctor --brief` 不是 `blocked` |
| [ ] | beta-check 通过 | `beta-check` 成功 |
| [ ] | 飞书测试收到 | `feishu-test` 成功 |
| [ ] | 值守启动 | `sudo systemctl status firemoney-beta-watch --no-pager` |
| [ ] | 健康检查输出 ready | `bash scripts/linux/check_firemoney_server.sh` |
| [ ] | 若提示缺 venv，先补系统包 | `sudo apt install -y python3-venv python3-pip` |

## 一条验收命令

部署完成后，在服务器里直接跑这一条：

```bash
cd /opt/firemoney && \
sudo systemctl status firemoney-preview --no-pager && \
sudo systemctl status firemoney-beta-watch --no-pager && \
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief && \
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20 && \
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20 && \
bash scripts/linux/check_firemoney_server.sh
```

你看到这些关键字就算通过：

- `preview`
- `beta-watch`
- `schedule-health`
- `notifications`
- `paper-db`
- `preview_http_ok`

## 服务器常用命令

```bash
sudo systemctl status firemoney-preview --no-pager
sudo systemctl status firemoney-beta-watch --no-pager
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20
bash scripts/linux/check_firemoney_server.sh
```

## 出问题先看

| 问题 | 先查什么 |
|---|---|
| 网页打不开 | `firemoney-preview` 和 `ss -ltnp 'sport = :8765'` |
| 早评晚评没发 | `schedule-health --brief` |
| 飞书没收到 | `feishu-test` |
| 值守没起来 | `firemoney-beta-watch` |

## 结束标准

| 状态 | 标准 |
|---|---|
| [ ] | 预览页能打开 |
| [ ] | 飞书能收到测试消息 |
| [ ] | 值守服务常驻 |
| [ ] | 没有重复实例 |
| [ ] | `schedule-health` 正常 |
| [ ] | 你能用这一页完成下一次部署 |
