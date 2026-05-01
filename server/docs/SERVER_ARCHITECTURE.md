# FireMoney 服务器/业务层架构

## 1. 目标

服务器/业务层负责可信规则、状态流转和外部系统适配。首版可以运行在本地进程内，但边界按服务端方式设计。

## 2. 当前骨架

```text
server/firemoney_server/
  application/
    main_chain.py       主链用例编排
  domain/
    opportunity.py      机会排序
    risk.py             执行前风控审查
    execution.py        半自动委托草稿和回执准备
    recap.py            执行复盘
  infrastructure/
    sample_data.py      第一条 smoke 的确定性样本数据
```

## 3. 分层规则

- `application` 负责编排，不写 UI。
- `domain` 负责业务规则，不依赖文件、SDK、窗口控件。
- `infrastructure` 负责数据源、SDK、文件、CSV、外部桥接。
- `shared/contracts` 是对客户端公开的稳定语言。

## 4. 首版主链

`MainChainService.build_first_slice_snapshot()` 跑通：

```text
市场上下文
-> 候选机会排序
-> 选出首个机会
-> 风控审查
-> 委托草稿
-> 半自动执行回执准备
-> 复盘改进建议
```

## 5. 后续迁移规则

- 旧项目的扫描、推荐、回测、执行、复盘能力必须按领域模块迁移。
- 不允许把旧项目大文件原样搬入服务端。
- 任何 SDK、券商、CSV 细节先进入 `infrastructure`，再由 application 调用。
- 风控、仓位、阻断、回执和复盘必须由服务端/业务层权威输出。
