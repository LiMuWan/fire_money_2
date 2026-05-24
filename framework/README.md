# FireMoney Framework

`framework/` 是可复用工程基础层，只沉淀和 FireMoney 股票业务无关的能力。

---

## 可以放什么

- JSON/config 加载辅助。
- append-only 本地记录存储。
- SQLite migration helper。
- scheduler state / due window 基础能力。
- notification transport 抽象。
- 未来 HTTP/RPC 边界占位。

---

## 不可以放什么

- 股票策略规则。
- A 股交易日历。
- FireMoney DTO。
- AkShare adapter。
- Feishu 产品适配器。
- 客户端 UI 渲染。

---

## 当前目录

```text
config/          通用配置加载
storage/         JSON store、SQLite migration
scheduler/       状态存储、due window 判断
notification/    通知结果模型和抽象
http/            未来网络边界占位
```

---

## 验证方式

```powershell
python -B -m unittest tests.test_application_boundaries -v
```
