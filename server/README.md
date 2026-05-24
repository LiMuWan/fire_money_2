# FireMoney 服务端

服务端负责主线首板的可信规则、状态变化、模拟盘账本和外部系统适配。当前可以在本地进程内运行，但边界按服务端方式设计。

---

## 模块定位

服务端负责：

- 加载主线策略配置。
- 归一化 AkShare 行情。
- 筛选和评分主板 10cm 首板候选。
- 生成早评、指挥单、盘中事件和晚评。
- 维护模拟盘 JSON/SQLite 账本。
- 执行飞书低噪音通知规则。
- 输出医生检查、稳定性复盘和部署健康状态。

服务端不负责：

- 渲染 UI。
- 连接真实券商账户。
- 自动实盘下单。
- 把飞书密钥或本地账本提交到仓库。

---

## 分层结构

```text
firemoney_server/
  application/          每日决策、模拟盘、通知、复盘和值守编排
  domain/               评分、拦截、位置结构、仓位和卖点纪律
  infrastructure/       行情、飞书、本地文件、SQLite、配置和交易日历
  infrastructure/config/one_to_two_strategy.zh_CN.json
```

---

## 核心入口

| 入口 | 职责 |
|---|---|
| `main_chain.py` | 对外组合入口，保持薄编排 |
| `strategy_decision_service.py` | 主线或空仓 |
| `paper_decision_service.py` | 只读模拟盘指挥单 |
| `watch_phase_service.py` | scan / auction / open / risk 阶段 |
| `notification_orchestrator.py` | 飞书发送资格和通知审计 |
| `doctor_review_service.py` | 行情、飞书、账本和调度预检 |

---

## 验证方式

```powershell
python -B -m unittest tests.test_main_chain_smoke -v
python -B -m unittest tests.test_strategy_decision_service -v
python -B -m unittest tests.test_notification_orchestrator -v
```
