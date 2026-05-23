# FireMoney 腾讯云部署一页清单

适合你现场照着勾选，不需要翻长文。

## 先确认

- [ ] 腾讯云实例已重置密码
- [ ] SSH 密钥已绑定到实例
- [ ] 安全组已放行 `22/tcp`
- [ ] 如需公网访问，`8765/tcp` 只对你的固定 IP 放行
- [ ] 本机私钥存在：`%USERPROFILE%\.ssh\firemoney_tencent`

## 一键部署

在 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_tencent_ubuntu_one_click.ps1
```

默认参数：

- IP：`81.70.202.132`
- 用户：`ubuntu`
- 私钥：`%USERPROFILE%\.ssh\firemoney_tencent`
- 分支：`codex/one-to-two-core-prune`

## 部署后立刻检查

- [ ] `firemoney-preview` 已启动
- [ ] `http://127.0.0.1:8765/core_workflow.html` 能看到 FireMoney
- [ ] `doctor --brief` 不是 `blocked`
- [ ] `beta-check` 通过
- [ ] `feishu-test` 已收到飞书消息
- [ ] `firemoney-beta-watch` 已启动
- [ ] `bash scripts/linux/check_firemoney_server.sh` 输出 `ready`

## 服务器上常用命令

```bash
sudo systemctl status firemoney-preview --no-pager
sudo systemctl status firemoney-beta-watch --no-pager
cd /opt/firemoney
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli notifications --action-only --brief --limit 20
/opt/firemoney/.venv/bin/python -B -m client.desktop.firemoney_client.one_to_two_cli paper-db --brief --limit 20
bash scripts/linux/check_firemoney_server.sh
```

## 如果出问题

- 网页打不开：先看 `firemoney-preview` 和 `ss -ltnp 'sport = :8765'`
- 早评晚评没发：先跑 `schedule-health --brief`
- 飞书没收到：先跑 `feishu-test`
- 值守没起来：先看 `firemoney-beta-watch`

## 这次部署结束的标准

- [ ] 预览页能打开
- [ ] 飞书能收到测试消息
- [ ] 值守服务常驻
- [ ] 没有重复实例
- [ ] `schedule-health` 正常
- [ ] 你能用这一页完成下一次部署
