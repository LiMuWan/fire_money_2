# FireMoney 客户端

客户端只负责用户体验和展示，不承担可信交易裁决。

---

## 模块定位

客户端负责回答：

- 今天的核心结论是什么？
- 模拟盘指挥单怎么看？
- 哪些候选、收益曲线、风险和证据需要展示？
- CLI 和预览页如何把服务端结果讲清楚？

客户端不负责：

- 重新计算买点和卖点。
- 直接读取 AkShare 字段。
- 直接读写 `.firemoney` 账本。
- 管理飞书密钥。

---

## 目录结构

```text
desktop/firemoney_client/
  cli/                 CLI parser、handler、output
  presenters/          brief、通知、高亮和信任状态展示
  adapter.py           本地服务端适配器
  composition.py       客户端依赖组合
  gateway.py           未来本地/HTTP 网关边界
  preview.py           生成预览 HTML
  renderer.py          页面总入口
  render_sections.py   页面区块
  static/core.css      预览页样式

desktop/preview/
  README.md            生成物目录说明
```

---

## 核心入口

```powershell
python -B -m client.desktop.firemoney_client.one_to_two_cli strategy-decision --sample-data --brief
python -B -m client.desktop.firemoney_client.one_to_two_cli paper-decision --sample-data --brief
python -B -m client.desktop.firemoney_client.preview
```

---

## 边界红线

1. UI 只消费 `shared/contracts` 和服务端 application 输出。
2. 页面里出现的买卖结论必须来自服务端。
3. 生成的 HTML、截图、JSON、SQLite 都不提交到 Git。
4. 新页面必须先让用户一眼看懂买、卖、空仓、风险和下一步。
