# FireMoney 封板波段主经营线迁移方案

## 目标
把产品默认经营重心从“主板 10cm 一进二纪律验证”逐步迁移到“封板波段体系”，同时保留一进二作为值守和样本沉淀线。

执行清单见 [BOARD_SHADOW_MAINLINE_EXECUTION_CHECKLIST.md](./BOARD_SHADOW_MAINLINE_EXECUTION_CHECKLIST.md)。

## 当前结论
- 一进二值守线更适合做日常纪律、飞书通知、模拟盘事件和闭环样本沉淀。
- 封板波段体系在 2024-01-01 到 2026-05-05 的无未来函数验证中，均衡低回撤 v2 固定 8% 仓位复合约 85.27%，动态 8%/12% 仓位复合约 100.32%，显著强于当前一进二默认线。
- 封板波段体系仍缺分钟线/Tick、封单排队、滑点和更强的可成交性验证，因此当前只适合作为经营主线候选，不直接宣称可实盘。

## 迁移原则
- 不删除一进二值守线，先让它退居“纪律值守线”。
- 不在没有分钟线/Tick 的前提下把封板波段直接切成唯一模拟盘执行线。
- 所有迁移都先让产品叙事、复盘和经营动作切换，再考虑交易执行切换。
- 每次迁移后都用同一套 2024+ 口径重跑回测和 walk-forward 验证。

## 分阶段计划
### 阶段 1：经营叙事迁移
- README、产品文档、Beta 计划、预览页统一写清楚：一进二是值守线，封板波段是经营线。
- 每日建议命令默认包含 `board-shadow-system --brief`。
- 尾盘复盘默认提示封板波段体系当前验证收益。

### 阶段 2：复盘入口迁移
- 在尾盘复盘和稳定性观察里增加封板波段体系摘要。
- 每日复盘默认同时看一进二闭环样本和封板波段经营收益口径。
- 用 `board-shadow-record` 继续沉淀 30/50/100 笔影子样本。

### 阶段 3：模拟盘前置验证
- 接入分钟线/Tick。
- 接入封单强度、开板次数和排队可成交验证。
- 增加真实滑点和成交失败近似。
- 重新评估封板波段体系是否可以升级成正式模拟盘主线。

### 阶段 4：执行主线迁移
- 只有在分钟线/Tick 和影子样本都通过后，才讨论把封板波段升级成默认模拟盘执行线。
- 一进二保留为辅线，用于纪律观测和对照验证。

## 今日可执行动作
- 运行 `python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-system --start-date 2024-01-01 --brief`
- 运行 `python -m client.desktop.firemoney_client.one_to_two_cli scheduler-runs --limit 20`
- 运行 `python -m client.desktop.firemoney_client.one_to_two_cli notifications --limit 20`
- 收盘后查看 `eod` 和 `board-shadow-record`

## 不该做的事
- 不要因为某一天空仓就放宽买点。
- 不要在没有分钟线/Tick 的前提下宣传“单票做 T 能稳定赚钱”。
- 不要把样本内收益最高的参数直接当成默认规则，必须先过 walk-forward。
