# FireMoney 模拟盘 Beta 上线检查

## 商用上线门槛

当前产品只允许定位为内部自用研究或模拟盘 Beta。只要没有完成持牌投顾合作、用户协议、风险揭示和合规审核，就不能对外收费提供具体股票买入/卖出建议，也不能宣传“保证稳定盈利”。

预览页证据中心新增“上线验收”页，统一展示六个硬门槛：

- 合规边界：未完成持牌/协议/风险揭示前，商用状态必须为阻断。
- 服务稳定：连续 30 个交易日服务、调度、行情、飞书和值守不断档。
- 飞书送达：早评、真实模拟买入、真实模拟卖出、晚评关键通知有 sent 审计记录，送达率接近 100%。
- 真实模拟盘：至少 30 笔真实闭环样本，胜率、收益、最大回撤和赚撤比一起达标。
- 回测证据：2020 起逐年回测、验证段、弱年份、最大回撤和执行摩擦压力测试都可复核。
- 产品边界：默认只展示主线首板、主板票、模拟盘、证据中心和风控纪律，不把研究线包装成可交易策略。

上线验收页出现 `暂不能对外商用` 时，不应继续包装销售；出现 `内部 Beta` 时，只能邀请极小范围试用并继续收集真实样本；只有全部门槛通过且合规完成后，才考虑小范围商业试点。

## 30 日真实值守验收口径

上线验收里的 `30日值守` 不看样例预览，只看真实审计记录自动累积：

- `覆盖交易日`：同一交易日必须同时存在早评 `morning` 和晚评 `eod` 的 `sent` 记录。
- `连续覆盖`：从最新覆盖交易日倒推，按交易日连续不断档统计。
- `买卖通知`：真实模拟买入 `watch:open` 和真实模拟卖出 `watch:risk` 都算关键送达，不能再用旧的 `watch` 汇总口径漏算。
- `闭环交易`：只看真实模拟盘数据库里的 closed trade，不把预览样例收益当真实收益。

30 日验收通过也不代表可以宣传保证盈利；它只证明系统在早评、买卖点、晚评、账本闭环和审计记录上连续稳定运行过。

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

当前候选规则为：非一字封板、成交额不低于 8000 万、均线多头、近 20 日涨幅不高于 20%、封板家数在 20 到 150 家、当天可见强度分排序，每天最多一只；卖点为普通市场次日 5.5% 止盈、强市场 8% 止盈、6% 止损、最多持有 1 个交易日。2020-01-01 到 2026-05-05 日线代理为 726 笔，胜率约 68.03%，8%/12% 动态仓位复合约 +96.96%，最大回撤约 -1.73%，7 个自然年均为正。它是当前唯一保留在经营面的主线，不是实盘收益保证。

新增执行摩擦压力测试：`paper-backtest` 同时展示 0.15%、0.30%、0.50%、0.80%、1.00% 往返成本。1.00% 成本下全区间仍约 +182.30%，验证段约 +7.94%，但最弱的 2021 仅约 +1.71%，因此压力状态为 warning；真实盘口若预估滑点接近或超过该压力，需要降低仓位或跳过。

每天可以用影子入口看封板线当天会不会出候选；它只读历史缓存，不写一进二模拟盘，不发交易指令：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow --trade-date 2026-04-29 --brief
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-record --trade-date 2026-04-29 --brief
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-stability --brief
python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-system --start-date 2024-01-01 --end-date 2026-05-05 --brief
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

   `beta-check` 会先验证飞书真实送达，再运行严格体检；不触发模拟买入或卖出。返回 `ready` 才能进入值守。HTTP 200 但飞书业务返回码失败也按 `failed` 处理。飞书适配器会自动重试 DNS、连接和超时类瞬时网络错误；如果早评或晚评最终仍失败，调度器不会把该关键通知标记为完成，会在当日窗口内继续重试。

4. 如需拆开排查，可手动运行飞书测试和上线前体检。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli feishu-test
   python -m client.desktop.firemoney_client.one_to_two_cli doctor --beta --market-data-timeout-seconds 20
   ```

   `strategy_config`、`trading_day`、`market_data`、`paper_store`、`notification_store`、`feishu`、`scheduler`、`scheduler_state`、`scheduler_runs` 必须全部为 `ready`。Beta 体检会要求当前交易日已有 `feishu-test` 的 `sent` 记录。

5. 先用不发通知模式做一次真实行情空跑。

   ```powershell
   python -m client.desktop.firemoney_client.one_to_two_cli morning --brief --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase scan --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase auction --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase open --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli watch --phase risk --no-notify
   python -m client.desktop.firemoney_client.one_to_two_cli eod --no-notify
   ```

   早评 `--brief` 必须是可读摘要，而不是 JSON 调试输出；本地至少能看到消息精华、资金动向、操作解读和重点候选的“股票名（代码）”。
   早评、策略决策和纸面指挥单允许同一交易日本地缓存兜底，避免行情源短暂超时被误判为防守空仓；但 `watch --phase open/risk` 必须依赖实时行情，不能用缓存写模拟买入或卖出。

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

本地调度器会按 08:50 早盘、盘中 `scan/auction/open/risk`、15:10 尾盘推进同一条一进二主线，并在 15:20 自动执行 `board-shadow-record`：用当日已经可见的 T+1 日线，记录上一交易日封板影子线样本到 `.firemoney/board_shadow_samples.json`，同时发飞书 shadow 复盘。这个 shadow 任务只做验证，不写入 `.firemoney/paper_trades.json`，不代表实盘交易指令。调度器会用 `.firemoney/scheduler_state.json` 防止同日重复触发，同时把每次调度结果写入 `.firemoney/scheduler_runs.json` 便于复核值守覆盖率。`schedule --beta` 仍可用于工程排查，正式上线测试优先使用 `beta-start`。

Beta 值守不能和 `--no-notify` 同时使用；盘中事件必须能触达到飞书。

## 运行稳定性和漏发排查

本地值守分三层，避免“服务今天开、明天不开”：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_firemoney_runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ensure_firemoney_runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_firemoney_runtime_watchdog.ps1
```

`check_firemoney_runtime.ps1` 只做体检：检查 `127.0.0.1:8765` 页面是否 200、预览服务是否只有一个监听实例、交易日 `beta-start --loop` 是否常驻、`schedule-health` 是否能解释早评、09:00 指挥单、09:31 开盘确认和晚评覆盖。预览页以 HTTP 200 为主判据，端口枚举只用于发现多实例，避免 Windows 网络 cmdlet 偶发不可读时误报客户端坏了。`ensure_firemoney_runtime.ps1` 是统一守护脚本：预览服务缺失时会补启，交易日发现 `beta-start --loop` 没在跑时会请求补启；非交易日只显示早评/晚评不应发送，不强行启动值守。Beta 值守用进程命令行和 `FireMoneyBetaWatch` 互斥锁双重确认，重复触发也会被 Windows 任务的 `IgnoreNew`、预览端口检查和 Beta 值守互斥锁挡住。`register_firemoney_runtime_watchdog.ps1` 优先注册开机和周期性巡检计划任务；如果系统策略拒绝注册计划任务，会退化为当前用户 Startup 快捷方式并写入 `.firemoney/logs/firemoney_startup_registration.log`。

如果某天没收到早评或晚评，先运行：

```powershell
python -B -m client.desktop.firemoney_client.one_to_two_cli schedule-health --brief
```

输出会区分四类情况：非交易日不该发、尚未到执行时间只等待值守触发、调度没运行、调度运行了但飞书没有 `sent` 记录。盘前看到 `pending` 是正常等待，不是漏发；过了执行窗口仍没有 `sent` 才需要按提示排查。不要在盘后补发早评；应该修复自启动、飞书配置或行情门禁，保证下一交易日按时运行。

腾讯云 Ubuntu 服务器使用 `docs/project/operations/TENCENT_CLOUD_UBUNTU_DEPLOYMENT.md` 的 systemd 部署方式：`firemoney-preview` 负责页面，`firemoney-beta-watch` 负责交易日值守；两个服务都读取 `/etc/firemoney/firemoney.env`，并通过 `flock` 防止重复实例。

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
- 暂无真实闭环样本或未达到复盘门槛时只允许降档小仓验证，不能因为样例回测好看就恢复常态仓位。
- 同类买点质量段样本未达到复核门槛时也只允许降档小仓验证，不能用其他买点段的收益替代本段证明。
- 达到 30/50/100 笔后再按稳定性报告调整一进二边界。
- 任何时候都只做模拟盘验证，不连接真实账户，不自动下单。
- 今日可执行候选超过 18 个时视为主线过散，只记录观察，不生成模拟买入。
- 卖点纪律默认：结构/4% 止损，12% 第一止盈，10% 强势阈值后 2% 回撤保护，2 个交易日不走强退出。
- 主线持续性默认：同主线候选、近涨停强度、AkShare 个股新闻和市场温度共同评分；低于 45 分则 T+1 优先退出。
- 回测准入默认：先跑 `backtest-audit --brief`；数据窗口不足、无闭环样本直接 blocked，样本少于 30 笔只能观察。
- 研究回测股票池少于 2500 只主板样本时必须中止或用本地历史缓存补齐，不能把缺失交易所样本的结果当作正式胜率。
- 封板验证线进入模拟盘前必须补：封单强度、开板次数、可成交排队、分钟线滑点、主线消息持续性；未补齐前不得替代当前一进二 Beta 主线。
- 封板影子线默认只在封板日市场封板家数 20 到 150 家之间记录样本；过冷或过热只观察，并在飞书/CLI 中展示封板家数、触板家数和上涨占比。
- 封板影子线默认拦截近 20 日涨幅超过 20% 的高位加速板；这类票即使封住也只观察，不写入 shadow 样本。
