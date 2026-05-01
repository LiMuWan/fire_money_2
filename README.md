# FireMoney

FireMoney 是围绕短线/盘中交易者重新开发的交易辅助终端。当前产品方向锁定为主板 10cm “一进二”战法验证：看懂市场、筛出昨日首板里最值得观察的一进二候选、用事件驱动模拟盘执行纪律、通过飞书通知和尾盘复盘沉淀稳定性。

核心业务线：

```text
市场判断 -> 执行中控 -> 复盘改进
```

这三段内部承载的真实动作已经切到一进二验证：

```text
早盘判断 + 昨日首板池 + 一进二候选
-> 竞价/盘中事件 + 模拟买入 + T+1 风险纪律
-> 尾盘测评 + 样本归档 + 稳定性观察
```

## 目录结构

```text
client/
  desktop/        桌面客户端，负责 UI、交互、确认和状态展示
  docs/           客户端设计和实现文档

server/
  docs/           服务端/业务层设计和实现文档

shared/
  contracts/      客户端和服务端共享契约、DTO、schema
  docs/           共享协议、数据字典和配置规范

docs/
  common/         跨项目通用原则和协作规范
  project/        FireMoney 项目文档
  archive/        历史参考资料
```

## 开发原则

- 先做好用户主线，再扩展功能。
- 首版只保留三段主入口：`市场判断`、`执行中控`、`复盘改进`。
- 客户端只捕获用户意图、展示状态、承载确认和反馈。
- 服务端/业务层承载可信判断、风控、日志、回执和可复盘状态。
- 共享契约放在 `shared/contracts/`，避免客户端和服务端各自猜字段。
- 界面文案优先放到配置或共享内容文件，方便后续多语言。
- 文档和 TODO 是交付物的一部分。

## 当前状态

当前仓库已经打通一条本地可验证闭环：

```text
信号扫描 -> 风控审查 -> 委托确认 -> CSV 委托导出
-> 券商回执导入 -> 成交明细回写 -> 退出成交回写
-> 结果卡 -> 策略边界建议 -> 交易归档 -> 最近归档复查
```

一进二专项切片也已经接入：

```text
AkShare 行情边界 -> 一进二评分/拦截 -> 事件驱动模拟盘
-> 止损/T+1 风险事件 -> 飞书通知结果 -> 尾盘测评 -> 稳定性报告
```

客户端入口仍然只保留三段核心工作区，辅助能力以当前决策上下文出现，不扩展成分散注意力的独立中心。

本地运行状态：

- 预览页：`client/desktop/preview/core_workflow.html`
- 文案配置：`client/desktop/firemoney_client/content/zh_CN.json`
- 策略边界：`.firemoney/strategy_config.json`
- 交易归档：`.firemoney/trade_archives.json`
- 委托/回执/成交样本：`exports/`
- 归档导出：`exports/archives/trade_archives.json` 或 `exports/archives/trade_archives.csv`
- 归档复查导出：`exports/archives/trade_archive_review.md`
- 策略边界审计导出：`exports/strategy/strategy_boundary_audit.md`
- 一进二策略配置：`server/firemoney_server/infrastructure/config/one_to_two_strategy.zh_CN.json`
- 一进二模拟盘账本：`.firemoney/paper_trades.json`
- AkShare 原始快照缓存：`.firemoney/market_data/`
- 策略边界审计可由服务端按 `apply`、`reset` 等变更动作筛选导出，客户端不读取 `.firemoney` 历史文件。
- 归档/策略导出清理由服务端按保留数量执行，只处理项目已知导出文件名，不直接清空整个 `exports/` 目录。

券商执行目前走项目自有 `BrokerExecutionAdapter` 边界，首个实现是本地 CSV；后续真实 SDK 必须先实现这个边界再接入主链。

归档复查目前是服务端轻量摘要：样本质量、胜率、累计盈亏、最佳样本、最弱样本和下一步建议都由业务层产生。少于 3 笔闭环归档只作为观察样本，不驱动策略边界调整；达到门槛后的策略边界审查只生成待用户确认的建议。只有显式确认后，服务端才会应用并持久化策略配置；策略回退也先生成可确认的回退审查，再由服务端恢复默认边界。应用/回退记录可导出为轻量审计报告。客户端只展示审查结果或触发导出，不扩展成独立历史中心。

## 配置入口

可见文本和演示样例优先走配置文件，代码只消费配置键和共享契约，避免把业务文案散落在 Python 实现里：

- 客户端界面文案：`client/desktop/firemoney_client/content/zh_CN.json`
- 本地预览样例输入：`client/desktop/firemoney_client/content/preview_seed.zh_CN.json`
- 服务端业务消息：`server/firemoney_server/domain/messages/zh_CN.json`
- 首版确定性样例行情和机会：`server/firemoney_server/infrastructure/config/sample_trading_data.zh_CN.json`
- 本地策略边界状态：`.firemoney/strategy_config.json`
- 本地交易归档状态：`.firemoney/trade_archives.json`

本地策略边界会在服务端进入下一轮扫描前校验；未知参数、类型错误和越界值会按默认边界纠偏。

一进二运行入口：

```powershell
python -m client.desktop.firemoney_client.one_to_two_cli morning --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli watch --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli eod --no-notify
python -m client.desktop.firemoney_client.one_to_two_cli backtest
```

飞书群机器人只读环境变量，不写入仓库：

- `FEISHU_ENABLED=true/false`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_WEBHOOK_SECRET` 可选

本地看效果可以加 `--sample-data` 使用确定性样例；真实入口默认走 AkShare，AkShare 不可用时报告进入 blocked 状态，不产生模拟买入。

新增功能时，如果文本、标签、提示、样例数据可以进入上述配置层，就不要写死在客户端、服务端或共享契约代码里。

运行测试：

```powershell
python -m unittest discover -s tests -v
```

重新生成本地预览：

```powershell
python -m client.desktop.firemoney_client.preview
```

## 下一步

短期不扩成多战法。下一步只围绕一进二专项补强：更完整的 AkShare 昨日涨停池/历史日线字段、常驻盘中扫描调度器、稳定性样本达到 30/50/100 笔后的策略边界建议。
