# FireMoney

FireMoney 是围绕短线/盘中交易者重新开发的交易辅助终端。首版只专注一条用户最核心的业务线：看懂市场、处理一个最值得处理的机会、确认执行、看见结果、沉淀改进。

核心业务线：

```text
市场判断 -> 执行中控 -> 复盘改进
```

这三段内部承载的真实动作是：

```text
全局态势 + 信号扫描 + 机会池
-> 执行审查 + 委托确认 + 回执跟踪
-> 单票复盘 + 策略边界改进
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

客户端入口仍然只保留三段核心工作区，辅助能力以当前决策上下文出现，不扩展成分散注意力的独立中心。

本地运行状态：

- 预览页：`client/desktop/preview/core_workflow.html`
- 文案配置：`client/desktop/firemoney_client/content/zh_CN.json`
- 策略边界：`.firemoney/strategy_config.json`
- 交易归档：`.firemoney/trade_archives.json`
- 委托/回执/成交样本：`exports/`

## 配置入口

可见文本和演示样例优先走配置文件，代码只消费配置键和共享契约，避免把业务文案散落在 Python 实现里：

- 客户端界面文案：`client/desktop/firemoney_client/content/zh_CN.json`
- 本地预览样例输入：`client/desktop/firemoney_client/content/preview_seed.zh_CN.json`
- 服务端业务消息：`server/firemoney_server/domain/messages/zh_CN.json`
- 首版确定性样例行情和机会：`server/firemoney_server/infrastructure/config/sample_trading_data.zh_CN.json`
- 本地策略边界状态：`.firemoney/strategy_config.json`
- 本地交易归档状态：`.firemoney/trade_archives.json`

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

短期不继续扩入口。下一步只在当前闭环上做小步增强：归档导出/清理、真实券商适配器、或更完整的策略边界验证。
