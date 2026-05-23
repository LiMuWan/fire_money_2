# FireMoney 封板波段主经营线执行清单

## 目标
把“封板波段体系”从研究结论推进成产品默认经营动作，同时保留“一进二”作为值守和样本沉淀线。

## 当前状态
- 已完成：`board-shadow-system --brief` 入口、预览面板、`beta-plan` 建议命令、尾盘复盘经营提示。
- 已完成：`beta-start` 真实行情值守跑通到 `2026-05-06` 的 `11:00 watch:risk`。
- 进行中：把产品默认叙事从“一进二中心”迁到“值守线 + 经营线”双层结构。
- 未完成：分钟线/Tick、封单排队、滑点验证，以及封板波段正式模拟盘主线切换。

## P0
### 默认叙事
- 把首页、README、产品文档统一成：
  值守线：一进二纪律验证
  经营线：封板波段体系
- 保留一进二文案，但降级为“纪律值守”和“闭环样本”角色。

### 每日动作
- `beta-plan --brief` 默认展示 `board-shadow-system --brief`。
- `eod` 默认提示封板波段体系当前验证收益。
- 日常复盘命令固定为：
  `python -m client.desktop.firemoney_client.one_to_two_cli board-shadow-system --start-date 2024-01-01 --brief`
  `python -m client.desktop.firemoney_client.one_to_two_cli scheduler-runs --limit 20`
  `python -m client.desktop.firemoney_client.one_to_two_cli notifications --limit 20`

### 真值守
- 保持 `beta-start --loop` 继续使用一进二主线做真实值守。
- 每天重点核对：
  `morning`
  `watch:scan`
  `watch:auction`
  `watch:open`
  `watch:risk`
  `eod`
  `board-shadow-record`

## P1
### 产品表层
- 让预览页、桌面页和说明文案默认出现封板波段体系摘要。
- 把“当前更值得经营的是哪条线”写成显式提示，而不是隐含在回测 JSON 里。

### 复盘表层
- 在尾盘复盘中并排展示：
  一进二今日是否执行
  封板波段体系当前长期验证收益
- 在稳定性观察里补一条“经营线提示”，避免只盯样本数。

### 文档表层
- 主策略文档保留一进二执行细节。
- 迁移方案文档负责写清楚切换条件。
- 执行清单负责列出真正下一轮要改的入口和文件。

## P2
### 切主线前必须补的能力
- 分钟线/Tick
- 封单强度和开板次数
- 排队可成交验证
- 真实滑点近似
- 更强的主线消息持续性证据

### 切主线前必须通过的验证
- `board-shadow-record` 至少积累 30/50/100 笔影子样本
- 与现有一进二值守线并行复核
- 同一套 2024+ 口径重跑 walk-forward
- 不能只看样本内最高收益，必须看验证段和执行可行性

## 今日继续观察
- `2026-05-06 14:00 watch:risk`
- `2026-05-06 14:50 watch:risk`
- `2026-05-06 15:10 eod`
- `2026-05-06 15:20 board-shadow-record`

## 不做
- 不因为单日空仓就放宽买点。
- 不在没有分钟线/Tick 的前提下宣传“主升浪启动前稳定埋伏”。
- 不把封板波段体系直接切成唯一实盘/模拟盘执行线。
