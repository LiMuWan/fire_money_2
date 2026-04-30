# FireMoney

FireMoney 是量化猎手 Pro 的重制项目。目标不是把旧项目完整搬过来，而是围绕一条清晰主链重新组织产品、客户端、服务器和公共契约。

核心定位：

**面向短线/盘中交易者的“机会发现 -> 决策审查 -> 执行中控 -> 复盘改进”交易辅助终端。**

核心主链：

```text
全局态势 -> 信号扫描 -> 机会池 -> 执行审查 -> 委托提交 -> 回执跟踪 -> 单票/日终复盘 -> 策略参数改进
```

## 目录结构

```text
client/
  desktop/        桌面客户端，负责 UI、交互、图表、确认、状态展示
  docs/           客户端专属设计和实现文档

server/
  docs/           服务端专属设计和实现文档

shared/
  contracts/      客户端和服务端共享契约、DTO、schema
  docs/           共享协议、数据字典、配置规范

docs/
  common/         跨项目通用原则、协作规范
  project/        FireMoney 项目文档
  archive/        从旧项目迁移过来的历史参考文档
```

## 重制原则

- 先产品主链，后功能扩张。
- 先分层，再细分功能。
- 客户端只做用户意图、展示、确认和反馈。
- 服务端/业务层优先承载可信规则、风控、状态、日志、复盘和外部 SDK 适配。
- 公共契约放入 `shared/contracts/`，避免客户端和服务端各自猜字段。
- 文档和 TODO 是交付物的一部分。
- 每个完整功能都要用 Git 独立提交。

## 文档入口

- [核心业务功能基准](C:/Users/18335/Documents/FireMoney/docs/project/product/CORE_BUSINESS_FUNCTIONS.md)
- [UI 商业化改造需求](C:/Users/18335/Documents/FireMoney/docs/project/ui/UI_COMMERCIAL_REQUIREMENTS.md)
- [终端级 UI 设计方案](C:/Users/18335/Documents/FireMoney/docs/project/ui/UI_WORLD_CLASS_TERMINAL_DESIGN_2026-04-19.md)
- [UI 解耦与重构规范](C:/Users/18335/Documents/FireMoney/docs/project/engineering/UI_DECOUPLING_REFACTOR_STANDARD_2026-04-20.md)
- [UI 改版 TODO](C:/Users/18335/Documents/FireMoney/docs/project/ui/UI_REDESIGN_TODO_2026-04-20.md)

## 当前状态

当前仓库只建立重制骨架和文档基准，尚未迁移旧项目代码。下一步应先制定客户端/服务器/共享契约的第一版技术方案，再选择性迁移旧项目里已经验证过的业务能力。
