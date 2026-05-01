# FireMoney Client

客户端只负责一进二产品体验，不承担可信业务裁决。

## 职责

- 展示一进二专项台：候选池、位置评分、止损/T+1、模拟盘、飞书通知、尾盘测评、稳定性观察。
- 捕获用户运行或查看意图，提供清晰状态反馈。
- 通过 `LocalMainChainAdapter` 消费服务端/业务层输出。
- 不直接读取 AkShare、飞书 Webhook 或 `.firemoney` 账本细节。
- 不保留旧 demo、旁支交易流或通用交易链路 UI。

## 结构

```text
desktop/
  firemoney_client/
    adapter.py        一进二客户端适配器
    one_to_two_cli.py 早盘、盘中、尾盘、稳定性本地入口
    preview.py        生成本地 HTML 预览
    renderer.py       一进二静态预览渲染
    static/           预览样式
  preview/            生成后的本地预览文件
docs/
  CLIENT_ARCHITECTURE.md
```

生成预览：

```powershell
python -m client.desktop.firemoney_client.preview
```
