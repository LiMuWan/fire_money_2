# FireMoney

2026-05-02 核心线更新：当前产品线已经收敛为 `主线首板龙头预判 -> 封板纪律确认 -> 次日一进二确认 -> 模拟盘验证 -> 尾盘复盘 -> 稳定性观察`。一进二不再作为孤立战法入口，而是作为首板候选次日强弱确认和 T+1 风险处理点。完整产品边界见 [docs/project/product/MAINLINE_FIRST_BOARD_STRATEGY.md](docs/project/product/MAINLINE_FIRST_BOARD_STRATEGY.md)。

FireMoney 当前只保留一条产品主线：主板 10cm “一进二”战法验证。

第一版目标不是自动实盘交易，而是验证战法稳定性：用 AkShare 边界接行情，筛昨日首板，判断低位/突破/压力，事件驱动模拟盘执行纪律，通过飞书通知早盘、盘中和尾盘结果，并沉淀稳定性样本。

核心业务线：

```text
早盘判断 -> 盘中模拟 -> 尾盘复盘 -> 稳定性观察
```

## 目录结构

```text
client/
  desktop/        一进二本地 CLI、预览生成和静态渲染
  docs/           客户端设计和实现文档

server/
  docs/           服务端/业务层设计和实现文档
  firemoney_server/
    application/  一进二用例编排
    domain/       一进二评分、拦截和风险规则
    infrastructure/ AkShare、飞书、模拟盘、策略配置

shared/
  contracts/      一进二共享契约和 DTO
  docs/           共享协议说明

docs/
  common/         跨项目通用原则和协作规范
  project/        FireMoney 项目文档
  archive/        历史参考资料
```

## 当前闭环

```text
MarketDataProvider/AkShare
-> 一进二评分与硬拦截
-> 交易日解析和阶段化 watch
-> PaperTradeStore 事件驱动模拟盘
-> 止损/T+1 风险事件和完成样本归档
-> FeishuNotifier 通知结果
-> 尾盘测评
-> 稳定性观察
```

默认边界：

- 只做 A 股主板 10cm 一进二。
- 排除 ST、退市、新股前 5 日、创业板、科创板、北交所。
- `min_score=82`，10 万模拟本金，单票最多 8%，每天最多 1 笔。
- 低位平台突破必须有市场宽度确认：昨日首板不少于 45 家，今日可执行候选不少于 6 个；宽度不足只观察不买入。
- 次日开盘确认必须红盘且不高于 3.5%；默认 4%/结构止损，12% 第一止盈，强势达到 10% 后用 2% 回撤保护。
- 当天跌破止损只发风险预警，次日仍低于止损才模拟卖出。
- 持仓满 2 个交易日仍未走强，进入纪律退出并归档样本。
- 稳定性统计基于完成交易样本，不再只按事件条数估算，并保留最近完成样本用于肉眼复盘。
- 样本少于 30 笔只显示观察期，不自动给策略边界结论；达到 30/50/100 笔后才输出阶段性边界建议。

## 配置与本地状态

- 依赖清单：`requirements.txt`
- 一进二策略配置：`server/firemoney_server/infrastructure/config/one_to_two_strategy.zh_CN.json`
- 模拟盘账本：`.firemoney/paper_trades.json`
- 飞书通知归档：`.firemoney/notifications.json`
- 调度去重状态：`.firemoney/scheduler_state.json`
- 调度运行审计：`.firemoney/scheduler_runs.json`
- AkShare 原始快照缓存：`.firemoney/market_data/`
- 本地预览：`client/desktop/preview/core_workflow.html`

模拟盘 Beta 上线前检查：`docs/project/product/BETA_LAUNCH_CHECKLIST.md`

飞书通知只读环境变量，不写入仓库。可以用群机器人 Webhook：

- `FEISHU_ENABLED=true/false`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_WEBHOOK_SECRET` 可选

也可以用飞书应用机器人：

- `FEISHU_ENABLED=true`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_RECEIVE_ID`
- `FEISHU_RECEIVE_ID_TYPE=chat_id`

本机可把这些值写在被忽略的 `.firemoney/feishu.env`，CLI 启动时会自动读取，进程环境变量优先级更高。

飞书消息由服务端业务层统一生成：早盘包含候选、拦截、止损和仓位上限；盘中包含事件、持仓、止损、T+1 状态、止损预警的次日处理计划、模拟盘提醒和刚完成的卖出/纪律退出样本；尾盘包含事件、预警、完成样本、最新样本摘要、稳定性阶段、下一样本门槛和服务端边界建议。

## 本地运行

首次准备真实行情入口：

```powershell
python -m pip install -r requirements.txt
$env:FEISHU_ENABLED="true"
$env:FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/..."
python -m client.desktop.firemoney_client.one_to_two_cli beta-check
python -m client.desktop.firemoney_client.one_to_two_cli beta-start --loop --interval-seconds 60
```

应用机器人模式也可以放入 `.firemoney/feishu.env`：

```text
FEISHU_ENABLED=true
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
FEISHU_RECEIVE_ID=oc_...
FEISHU_RECEIVE_ID_TYPE=chat_id
```

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli morning --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli eod --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli replay --brief --trade-date 2026-04-24 --holding-days 3
python -m client.desktop.firemoney_client.one_to_two_cli backtest --start-date 2026-04-01 --end-date 2026-04-30 --max-trade-days 20
python -m client.desktop.firemoney_client.one_to_two_cli stability
python -m client.desktop.firemoney_client.one_to_two_cli doctor
python -m client.desktop.firemoney_client.one_to_two_cli feishu-test --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli schedule --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli beta-start
python -m client.desktop.firemoney_client.one_to_two_cli notifications --limit 20
python -m client.desktop.firemoney_client.one_to_two_cli scheduler-runs --limit 20
```

盘中 watch 可按阶段手动推进：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase scan --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase auction --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase open --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase risk --no-notify
```

本地调度器只推进一进二主线，会按日内时间触发早盘、`scan`、`auction`、`open`、盘中 `risk` 和尾盘，并用 `.firemoney/scheduler_state.json` 防止同一交易日同一任务重复执行，同时把每次调度结果写入 `.firemoney/scheduler_runs.json` 便于复核值守覆盖率。错过执行窗口的任务会标记为 `expired`，不会在下午补跑开盘买入。本地试跑可以固定时间：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli schedule --trade-date 2026-04-30 --at 09:31 --sample-data --no-notify --paper-store .firemoney/tmp-paper.json --scheduler-state .firemoney/tmp-scheduler.json
python -m client.desktop.firemoney_client.one_to_two_cli beta-start --loop --interval-seconds 60
```

`beta-start` 会先运行严格 `doctor --beta` 门禁；只有策略配置、交易日、行情、本地账本、飞书 sent 记录和调度审计全部 ready，才会启动本次调度。失败时只输出体检报告，不写入调度状态，不产生模拟买入。

本地看效果可以加 `--sample-data` 使用确定性样例。真实入口默认走 AkShare；AkShare 不可用时报告进入 `blocked`，不产生模拟买入。

`beta-check` 是上线前一键预检，会先发送飞书测试，再运行 `doctor --beta`，不触发模拟买卖；返回 `ready` 后用 `beta-start` 值守。`doctor` 是运行前体检，只检查策略配置、行情源、本地状态文件、飞书和调度，不发送通知、不产生交易；Beta 模式会要求当前交易日已有一次 `feishu-test` 的 `sent` 记录。`feishu-test` 只验证飞书通知联通并归档结果，不触发模拟买卖。`schedule` 保留给工程排查，正式上线测试优先用 `beta-start`。`backtest` 使用隔离临时账本做历史回放，不会改写 `.firemoney/paper_trades.json`。`stability` 读取当前模拟盘已闭环样本，用来查看真实观察期累计质量。两类输出都遵守样本门槛：少于 30 笔只显示观察期。

查看飞书触达记录：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli notifications --workflow watch:open --status prepared --limit 10
python -m client.desktop.firemoney_client.one_to_two_cli scheduler-runs --limit 10
```

重新生成预览：

```powershell
python -m client.desktop.firemoney_client.preview
```

预览页使用隔离的临时模拟盘，会展示一进二候选、开盘模拟买入、盘中止损预警、T+1 处理纪律、尾盘测评和稳定性样本，不会改写真实 `.firemoney/paper_trades.json`。

运行测试：

```powershell
python -B -m unittest discover -s tests -v
```

## 开发原则

- 只保留一进二这条核心业务线。
- 客户端只展示服务端输出，不重新计算可信交易结论。
- 服务端/业务层承载评分、风控、模拟盘账本、通知结果和复盘结论。
- AkShare、飞书和本地文件都在基础设施层，策略和 UI 不依赖第三方字段名。
- 新功能必须让 `早盘判断 -> 盘中模拟 -> 尾盘复盘 -> 稳定性观察` 更清晰、更快或更可信。
