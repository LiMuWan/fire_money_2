# FireMoney 模拟盘 Beta 上线检查

## 2026-05-03 上线测试前彩排

先看只读上线计划，它会告诉你下一交易日、当前阻断项和建议命令，不发飞书、不改账本：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli beta-plan --brief
```

不加 `--brief` 会输出完整 JSON，适合排查字段和程序读取。

先运行隔离彩排，不发飞书、不污染真实 `.firemoney/paper_trades.json`：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli beta-rehearsal --trade-date 2026-04-30
```

`beta-rehearsal` 会用样例行情和临时账本跑完 `doctor -> morning -> scan -> auction -> open -> risk -> eod -> stability`。返回 `ready` 只代表主线流程、调度和模拟盘闭环能跑通；真实上线测试仍然必须在交易日运行 `beta-check`，确认飞书 `sent` 后再启动 `beta-start --loop --interval-seconds 60 --market-data-timeout-seconds 20`。

再运行回测准入审计，确认数据质量、样本数量和规则版本边界：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli backtest-audit --brief --max-trade-days 120
```

`backtest-audit` 会按“数据准备 -> 策略规则 -> 执行回测 -> 准入结论”输出结果。少于 30 笔闭环样本只允许观察；AkShare 免费数据暂不等同专业 Point-in-Time 数据，不能据此宣称长期稳定盈利。

如果要回答“从 2024 年到现在，这套一进二产品算法到底赚不赚钱”，使用研究脚本按产品执行口径回放。结论只看 `product_portfolio.one_position_no_overlap`，不要看“所有候选全买”：

```powershell
python -B tools\research_one_to_two_backtest.py --start-date 2024-01-01 --end-date 2026-05-03 --workers 12 --output exports\one_to_two_backtest_2024_to_now.json
```

当前默认研究口径包含 `min_score=82`、`max_execution_score=90`、0%-3.5% 次日开盘确认、单票 8%、每天最多 1 笔、严格 T+1。`max_execution_score=90` 是 2026-05-04 利润矩阵筛出的过热执行分拦截：执行侧分数过高不再模拟买入，避免一致性拥挤接力。2024-01-01 到 2026-05-03 的正式日线回测为 156 笔，胜率 48.08%，8% 仓位复合约 22.22%，最大回撤约 3.28%。这只用于 Beta 准入判断，不等同实盘盈利承诺。

如果要比较“继续一进二、改打板、做波段、做 T 哪条路线更值得产品化”，先跑战法矩阵。结论看 `one_position_no_overlap`，它按每天最多一只、单仓不重叠、只用当天可见字段排名；不要用所有信号全买口径：

```powershell
python -B tools\research_strategy_matrix_backtest.py --start-date 2024-01-01 --end-date 2026-05-03 --output exports\strategy_matrix_backtest_2024_to_now.json
```

2026-05-04 的路线矩阵显示，封板打板日线代理为 276 笔、胜率 53.62%、8% 仓位复合约 42.62%、最大回撤约 3.71%，三段年份均为正，是目前更高收益候选线；龙头首阴复合约 19.65% 但年份不稳定；低位平台突破复合约 2.35%；通用一进二竞价、触板未封追涨、常见波段代理均不适合作为当前核心线。封板路线暂列验证线，不直接上线实盘，因为日线不能证明封单、排队、滑点和真实可成交。

封板验证线继续用利润矩阵做买卖点搜索，必须同时通过训练期和 2026 验证期：

```powershell
python -B tools\research_limit_up_board_profit_matrix.py --start-date 2024-01-01 --end-date 2026-05-03 --top 20 --output exports\limit_up_board_profit_matrix_2024_to_now.json
```

当前候选规则为：非一字封板、成交额不低于 8000 万、均线多头、近 20 日涨幅不高于 35%、当天可见强度分排序，每天最多一只；卖点为次日 5% 止盈、6% 止损、最多持有 1 个交易日。2024-01-01 到 2026-05-03 日线代理为 272 笔，胜率 66.54%，8% 仓位复合约 66.10%，最大回撤约 3.41%，训练期约 +52.41%，2026 验证期约 +8.98%。它是下一阶段更高收益验证线，不是当前实盘上线条件。

每天可以用影子入口看封板线当天会不会出候选；它只读历史缓存，不写一进二模拟盘，不发交易指令：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow --trade-date 2026-04-29 --brief
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-record --trade-date 2026-04-29 --brief
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-stability --brief
```

单点检查某个历史交易日“当时介入、后面盈亏比”：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli replay --brief --trade-date 2026-04-24 --holding-days 3
```

`replay` 只用指定交易日当时的候选池做选股，后续日线只用于模拟 T+1 之后的卖点和盈亏比。它适合快速核对一笔样本的买卖纪律，但不能替代 30/50/100 笔稳定性统计。

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
   python -m client.desktop.firemoney_client.one_to_two_cli beta-check --market-data-timeout-seconds 20
   ```

   `beta-check` 会先验证飞书真实送达，再运行严格体检；不触发模拟买入或卖出。返回 `ready` 才能进入值守。HTTP 200 但飞书业务返回码失败也按 `failed` 处理。

4. 如需拆开排查，可手动运行飞书测试和上线前体检。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli feishu-test
   python -m client.desktop.firemoney_client.one_to_two_cli doctor --beta --market-data-timeout-seconds 20
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
python -m client.desktop.firemoney_client.one_to_two_cli beta-start --loop --interval-seconds 60 --market-data-timeout-seconds 20
```

`beta-start` 会先运行严格 `doctor --beta` 门禁；只有策略配置、交易日、行情、本地账本、飞书 sent 记录和调度审计全部 `ready`，才会启动调度。行情体检超过 `--market-data-timeout-seconds` 会快速返回 `blocked`。失败时只输出体检报告，不写入调度状态，不产生模拟买入。

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
- 今日可执行候选超过 18 个时视为主线过散，只记录观察，不生成模拟买入。
- 卖点纪律默认：结构/4% 止损，12% 第一止盈，10% 强势阈值后 2% 回撤保护，2 个交易日不走强退出。
- 主线持续性默认：同主线候选、近涨停强度、AkShare 个股新闻和市场温度共同评分；低于 45 分则 T+1 优先退出。
- 回测准入默认：先跑 `backtest-audit --brief`；数据窗口不足、无闭环样本直接 blocked，样本少于 30 笔只能观察。
- 研究回测股票池少于 2500 只主板样本时必须中止或用本地历史缓存补齐，不能把缺失交易所样本的结果当作正式胜率。
- 封板验证线进入模拟盘前必须补：封单强度、开板次数、可成交排队、分钟线滑点、主线消息持续性；未补齐前不得替代当前一进二 Beta 主线。
