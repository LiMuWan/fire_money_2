# FireMoney 共享契约 V1

## 1. 目的

共享契约定义客户端和服务器/业务层之间的共同语言，避免两边各自猜字段。

V1 只覆盖第一条主链 smoke：

```text
全局态势 -> 信号扫描 -> 机会池 -> 执行审查 -> 委托提交 -> 回执跟踪 -> 复盘改进
```

代码入口：

- `shared/contracts/trading.py`

## 2. 主要契约

### `MarketContext`

描述当前市场状态，回答“现在有没有机会、风险如何、下一步看哪里”。

关键字段：

- `trade_date`
- `market_temperature`
- `trend`
- `risk_level`
- `summary`
- `next_action`

### `Opportunity`

描述一个候选机会，回答“这只票为什么值得看”。

关键字段：

- `symbol`
- `name`
- `score`
- `confidence`
- `strategy_tags`
- `entry_price`
- `stop_loss`
- `target_price`
- `risk_flags`
- `rationale`

### `RiskReview`

描述执行前审查结论，回答“这笔交易能不能做、有什么风险”。

关键字段：

- `review_id`
- `decision`
- `risk_level`
- `position_limit_pct`
- `blockers`
- `warnings`
- `next_action`

### `OrderTicket`

描述待确认委托草稿，回答“系统准备提交什么”。

关键字段：

- `order_id`
- `review_id`
- `symbol`
- `side`
- `quantity`
- `limit_price`
- `route`
- `requires_confirmation`
- `status`

### `ExecutionReceipt`

描述执行回执，回答“委托准备/提交后结果是什么”。

关键字段：

- `receipt_id`
- `order_id`
- `accepted`
- `status`
- `message`
- `exported_path`

### `Recap`

描述执行复盘，回答“这次执行如何沉淀为改进”。

关键字段：

- `recap_id`
- `order_id`
- `conclusion`
- `execution_deviation`
- `lessons`
- `next_strategy_action`

### `StrategyConfig`

描述策略边界，回答“参数怎么影响风险和候选”。

关键字段：

- `strategy_id`
- `name`
- `version`
- `risk_profile`
- `parameters`
- `impact_summary`

### `MainChainSnapshot`

聚合主链快照，客户端只消费这个结构来展示主链状态，不在 UI 中重新判断业务结论。

## 3. 状态枚举

- `WorkflowStage`：主链阶段。
- `RiskLevel`：风险等级。
- `ReviewDecision`：执行审查结论。

## 4. 规则

- 新增跨端字段必须先更新共享契约和本文档。
- 客户端不得根据私有字段推断可信业务结果。
- 服务端/业务层必须返回足够支持 UI 展示的 `summary`、`next_action`、`status` 或等价字段。
- 交易相关契约默认支持半自动确认，不默认支持无审查自动交易。
