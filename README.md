# FireMoney

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
- `min_score=70`，10 万模拟本金，单票最多 8%，每天最多 1 笔。
- 当天跌破止损只发风险预警，次日仍低于止损才模拟卖出。
- 持仓满 2 个交易日仍未走强，进入纪律退出并归档样本。
- 稳定性统计基于完成交易样本，不再只按事件条数估算，并保留最近完成样本用于肉眼复盘。
- 样本少于 30 笔只显示观察期，不自动给策略边界结论；达到 30/50/100 笔后才输出阶段性边界建议。

## 配置与本地状态

- 一进二策略配置：`server/firemoney_server/infrastructure/config/one_to_two_strategy.zh_CN.json`
- 模拟盘账本：`.firemoney/paper_trades.json`
- 飞书通知归档：`.firemoney/notifications.json`
- AkShare 原始快照缓存：`.firemoney/market_data/`
- 本地预览：`client/desktop/preview/core_workflow.html`

飞书群机器人只读环境变量，不写入仓库：

- `FEISHU_ENABLED=true/false`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_WEBHOOK_SECRET` 可选

飞书消息由服务端业务层统一生成：早盘包含候选、拦截、止损和仓位上限；盘中包含事件、持仓、止损、T+1 状态、模拟盘提醒和刚完成的卖出/纪律退出样本；尾盘包含事件、预警、完成样本、最新样本摘要、稳定性阶段、下一样本门槛和服务端边界建议。

## 本地运行

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli morning --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli eod --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli backtest --start-date 2026-04-01 --end-date 2026-04-30 --max-trade-days 20
python -m client.desktop.firemoney_client.one_to_two_cli stability
python -m client.desktop.firemoney_client.one_to_two_cli doctor
python -m client.desktop.firemoney_client.one_to_two_cli schedule --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli notifications --limit 20
```

盘中 watch 可按阶段手动推进：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase scan --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase auction --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase open --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --phase risk --no-notify
```

本地调度器只推进一进二主线，会按日内时间触发早盘、`scan`、`auction`、`open`、盘中 `risk` 和尾盘，并用 `.firemoney/scheduler_state.json` 防止同一交易日同一任务重复执行。错过执行窗口的任务会标记为 `expired`，不会在下午补跑开盘买入。本地试跑可以固定时间：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli schedule --trade-date 2026-04-30 --at 09:31 --sample-data --no-notify --paper-store .firemoney/tmp-paper.json --scheduler-state .firemoney/tmp-scheduler.json
python -m client.desktop.firemoney_client.one_to_two_cli schedule --loop --interval-seconds 60
```

本地看效果可以加 `--sample-data` 使用确定性样例。真实入口默认走 AkShare；AkShare 不可用时报告进入 `blocked`，不产生模拟买入。

`doctor` 是运行前体检，只检查策略配置、行情源、模拟盘账本、飞书和调度状态，不发送通知、不产生交易。`backtest` 使用隔离临时账本做历史回放，不会改写 `.firemoney/paper_trades.json`。`stability` 读取当前模拟盘已闭环样本，用来查看真实观察期累计质量。两类输出都遵守样本门槛：少于 30 笔只显示观察期。

查看飞书触达记录：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli notifications --workflow watch:open --status prepared --limit 10
```

重新生成预览：

```powershell
python -m client.desktop.firemoney_client.preview
```

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
