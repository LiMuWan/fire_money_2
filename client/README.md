# FireMoney Client

客户端负责用户体验和操作闭环，不承担可信业务裁决。

## 职责

- 展示 `市场判断`、`执行中控`、`复盘改进` 三个核心入口。
- 把信号扫描和机会池收进 `市场判断`，把单票复盘和策略边界收进 `复盘改进`。
- 捕获用户意图，提供清晰的确认、取消、回退和状态反馈。
- 展示服务端/业务层返回的风控结论、委托建议、执行回执和复盘结果。
- 通过共享契约和服务端通信，不直接猜测字段。
- 通过内容配置承载可见文案，方便后续多语言。

## 非职责

- 不直接处理最终风控裁决。
- 不直接持有账户、持仓、委托的权威状态。
- 不把 SDK 或券商桥接细节写进 UI。
- 不在 UI 事件里堆业务规则。
- 不在首版提供分散用户注意力的消息中心、AI 中心、复杂统计中心。

## 初始结构

```text
desktop/
  firemoney_client/
    adapter.py    与服务端/本地业务层通信的客户端适配器
    content.py    内容配置加载
    content/      多语言文案配置
    preview.py    生成本地 HTML 预览
    renderer.py   把共享快照渲染为静态预览页
    shell.py      应用壳层、三段入口、主链状态展示
    view_model.py 把可信业务快照转成展示模型
    static/       预览样式
  preview/        生成后的本地预览文件
docs/
  客户端设计、交互和实现文档
```

## 当前体验边界

- 一个页面承载三段主线，不新增历史 dashboard 或消息中心。
- 交易状态通过按钮推进为本地预览状态：确认、提交回执、成交写回、退出写回、应用建议、恢复默认。
- 最近归档只作为侧栏复查条出现，帮助用户回忆闭环结果，不承担复杂检索。
- UI 不计算盈亏、止损纪律或策略建议，只展示服务端/共享契约结果。

## 内容配置

- `desktop/firemoney_client/content/zh_CN.json` 承载客户端可见文案、工作区标签、章节标题、空状态、按钮和页面模板。
- `desktop/firemoney_client/content/preview_seed.zh_CN.json` 承载本地 HTML 预览使用的券商回执、入场成交和退出成交样例。
- `desktop/firemoney_client/content.py` 只负责加载和校验内容结构；`shell.py`、`renderer.py`、`preview.py` 不再写业务中文文案。
- 后续增加语言时，优先新增同结构的内容文件，而不是复制 UI 代码。

生成预览：

```powershell
python -m client.desktop.firemoney_client.preview
```
