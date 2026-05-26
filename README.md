# FireMoney 主线首板

FireMoney 是一个面向 A 股主板 10cm 的主线首板研究与模拟盘值守项目。

项目当前只保留一条默认经营主线：`主线首板候选 -> 早盘指挥单 -> 盘中模拟买卖 -> 尾盘复盘 -> 收益与回撤证据`。它的目标不是替你自动实盘下单，而是把买点、卖点、仓位、飞书通知和回测证据放进同一条可验证闭环里。

> 风险说明：本项目只做研究、模拟盘和工程验证，不构成投资建议，不承诺盈利。任何实盘决策都需要你独立判断并承担风险。

---

## 项目能做什么

- 筛选主板 10cm 主线首板候选，默认聚焦 50-800 亿市值带。
- 生成早盘、盘中、尾盘和值守诊断报告。
- 给出模拟盘买入、卖出、仓位、止损、止盈和取消条件。
- 记录 JSON/SQLite 模拟盘账本，便于复盘每笔交易的收益和回撤。
- 只向飞书推送低噪音消息：早评、真实模拟买入、真实模拟卖出、晚评。
- 生成本地或服务器预览页，用一屏优先展示“今天买不买、卖不卖、风险在哪里”。
- 可选接入本机 QMT/MiniQMT：检查账户快照，把模拟盘指挥单转换为 dry-run 拟委托；实盘提交必须显式打开安全开关。
- 支持腾讯云 Ubuntu systemd 部署，保证预览服务和值守服务可自启、可检查、可复盘。

## 项目不做什么

- 默认不连接券商账户；QMT 只作为可选本地网关。
- 默认不自动实盘下单，QMT 提交必须同时使用 `--qmt-submit` 和 `FIREMONEY_QMT_ALLOW_LIVE=true`。
- 不把样例数据当真实收益。
- 不保证每笔交易盈利。
- 不把研究线当默认经营入口。

---

## 快速开始

```powershell
python -m pip install -r requirements.txt

python -B -m client.desktop.firemoney_client.one_to_two_cli strategy-decision --sample-data --brief
python -B -m client.desktop.firemoney_client.one_to_two_cli paper-decision --sample-data --brief
python -B -m client.desktop.firemoney_client.preview
```

打开本地预览服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_core_workflow_preview.ps1
```

浏览器访问：

```text
http://127.0.0.1:8765/core_workflow.html
```

如果要部署到腾讯云，请从这里开始：

- [腾讯云 Ubuntu 部署手册](docs/project/operations/TENCENT_CLOUD_UBUNTU_DEPLOYMENT.md)
- [腾讯云一页验收清单](docs/project/operations/TENCENT_CLOUD_UBUNTU_DEPLOYMENT_CHECKLIST.md)

---

## 文档入口

FireMoney 的公开手册采用中文编号命名，阅读顺序见：

- [docs/README.md](docs/README.md)

推荐第一次阅读顺序：

| 文档 | 用途 |
|---|---|
| [0-介绍.md](docs/0-介绍.md) | 项目定位、边界和当前阶段 |
| [1-快速开始.md](docs/1-快速开始.md) | 本地运行、预览、飞书测试 |
| [2-框架概览.md](docs/2-框架概览.md) | 客户端、服务端、共享契约和框架层 |
| [3-1-主线策略模块.md](docs/3-1-主线策略模块.md) | 候选筛选、买点、卖点、仓位边界 |
| [3-2-模拟盘与通知模块.md](docs/3-2-模拟盘与通知模块.md) | 模拟盘账本、飞书低噪音、复盘证据 |
| [3-3-部署与值守模块.md](docs/3-3-部署与值守模块.md) | Windows 本地值守和腾讯云 systemd |
| [99-运行与验证.md](docs/99-运行与验证.md) | 常用命令、自测和排障顺序 |
| [FAQ.md](docs/FAQ.md) | 常见问题 |

---

## 目录结构

```text
client/
  desktop/firemoney_client/   CLI、预览生成、页面渲染和客户端适配

server/
  firemoney_server/
    application/              每日决策、模拟盘、通知、复盘和值守编排
    domain/                   主线首板评分、拦截、仓位和风控规则
    infrastructure/           AkShare、飞书、本地账本、配置和交易日历

shared/
  contracts/                  客户端和服务端共享 DTO / 协议

framework/
  config/ storage/ scheduler/ notification/
                              可复用工程基础件，不依赖 FireMoney 业务

scripts/
  linux/                      腾讯云 Ubuntu systemd 部署和值守脚本
  *.ps1                       Windows 本地运行、检查和部署脚本

tests/
                              主线策略、模拟盘、通知、架构边界和部署脚本测试
```

## 分层红线

- `framework/` 不能导入 `server.firemoney_server`、`client` 或 FireMoney 交易 DTO。
- `client/` 只展示服务端输出，不重新计算可信交易结论。
- `server/firemoney_server/application/` 只做用例编排，不写页面渲染。
- `server/firemoney_server/domain/` 只放纯交易规则，不读文件、不发飞书、不访问 AkShare。
- `server/firemoney_server/infrastructure/` 负责外部系统适配，不把第三方字段泄漏给 UI。
- 运行态、截图、SQLite、飞书密钥和本地账本都不能提交到仓库。

## 运行态文件

这些文件默认被 `.gitignore` 忽略：

```text
.firemoney/
exports/
reports/
client/desktop/preview/*.html
client/desktop/preview/*.png
client/desktop/preview/*.json
client/desktop/preview/*.sqlite3
```

预览页、模拟盘账本、通知归档和运行状态都可以重新生成，不属于源码。

---

## 常用验证

```powershell
python -B -m unittest discover -s tests -v
python -B -m client.desktop.firemoney_client.one_to_two_cli doctor --brief --sample-data
python -B -m client.desktop.firemoney_client.one_to_two_cli strategy-decision --sample-data --brief
python -B -m client.desktop.firemoney_client.one_to_two_cli paper-decision --sample-data --brief
```

腾讯云服务器验收：

```bash
cd /opt/firemoney
bash scripts/linux/check_firemoney_server.sh
```

---

## 开源协作原则

- 先保证主线闭环可靠，再扩展研究能力。
- 新策略不能只看收益，必须同时看最大回撤、弱年份、验证段和样本质量。
- 任何通知改动都要保持低噪音，不把普通扫描消息推到飞书。
- 所有密钥、密码、运行账本和截图都留在本地或服务器，不进入 Git。
