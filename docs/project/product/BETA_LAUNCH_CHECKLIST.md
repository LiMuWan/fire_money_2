# FireMoney 模拟盘 Beta 上线检查

当前上线目标只到模拟盘 Beta：接真实行情、发飞书通知、沉淀一进二样本；不连接真实账户，不自动下单。

## 必过项

1. 安装依赖。

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. 配置飞书通知环境变量。

   ```powershell
   $env:FEISHU_ENABLED="true"
   $env:FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/..."
   ```

   `FEISHU_WEBHOOK_URL` 必须是飞书或 Lark 自定义机器人地址，不能用普通网页 URL 代替。

   如群机器人开启签名校验，再设置：

   ```powershell
   $env:FEISHU_WEBHOOK_SECRET="..."
   ```

   如果使用飞书应用机器人，则改为配置：

   ```powershell
   $env:FEISHU_ENABLED="true"
   $env:FEISHU_APP_ID="..."
   $env:FEISHU_APP_SECRET="..."
   $env:FEISHU_RECEIVE_ID="oc_..."
   $env:FEISHU_RECEIVE_ID_TYPE="chat_id"
   ```

   本机也可以把这些值放到被忽略的 `.firemoney/feishu.env`，CLI 启动时会自动读取，避免把密钥写入仓库。

3. 运行一键 Beta 预检。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli beta-check
   ```

   `beta-check` 会先验证飞书真实送达，再运行严格体检；不触发模拟买入或卖出。返回 `ready` 才能进入值守。HTTP 200 但飞书业务返回码失败也按 `failed` 处理。

4. 如需拆开排查，可手动运行飞书测试和上线前体检。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli feishu-test
   python -m client.desktop.firemoney_client.one_to_two_cli doctor --beta
   ```

   `strategy_config`、`trading_day`、`market_data`、`paper_store`、`notification_store`、`feishu`、`scheduler`、`scheduler_state`、`scheduler_runs` 必须全部为 `ready`。Beta 体检会要求当前交易日已有 `feishu-test` 的 `sent` 记录。

5. 先用不发通知模式做一次真实行情空跑。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli morning --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase scan --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase auction --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase open --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase risk --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli eod --no-notify
   ```

6. 确认通知和审计记录后再进入值守。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli notifications --limit 10
   python -m client.desktop.firemoney_client.one_to_two_cli scheduler-runs --limit 10
   ```

## Beta 值守命令

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli beta-start --loop --interval-seconds 60
```

`beta-start` 会先运行严格 `doctor --beta` 门禁；只有策略配置、交易日、行情、本地账本、飞书 sent 记录和调度审计全部 `ready`，才会启动调度。失败时只输出体检报告，不写入调度状态，不产生模拟买入。

本地调度器会按 08:50 早盘、盘中 `scan/auction/open/risk`、15:10 尾盘推进同一条一进二主线，并用 `.firemoney/scheduler_state.json` 防止同日重复触发，同时把每次调度结果写入 `.firemoney/scheduler_runs.json` 便于复核值守覆盖率。`schedule --beta` 仍可用于工程排查，正式上线测试优先使用 `beta-start`。

Beta 值守不能和 `--no-notify` 同时使用；盘中事件必须能触达到飞书。

## 不上线条件

- `doctor` 有任何 `blocked`。
- 当前不是 A 股交易日。
- AkShare 无法读取真实行情。
- `beta-check` 不是 `ready`，或飞书未启用、通知凭据未配置、当前交易日没有 `feishu-test` 的 `sent` 记录。
- `.firemoney/paper_trades.json` 不能读写。
- `.firemoney/notifications.json`、`.firemoney/scheduler_state.json` 或 `.firemoney/scheduler_runs.json` 不能读写。
- 没有先用 `--no-notify` 完成一次真实行情空跑。

## 观察期规则

- 少于 30 笔闭环样本只显示观察期，不给策略边界结论。
- 达到 30/50/100 笔后再按稳定性报告调整一进二边界。
- 任何时候都只做模拟盘验证，不连接真实账户，不自动下单。
