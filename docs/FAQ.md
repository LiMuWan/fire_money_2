# FAQ

## 这是自动炒股软件吗？

不是。FireMoney 当前只做研究、模拟盘和值守通知，不连接真实券商账户，不自动实盘下单。

## 为什么行情不可用时会防守空仓？

因为行情不可用时无法证明买点成立。系统宁愿少做，也不应该在数据不可信时生成模拟买入。

## 为什么飞书消息这么少？

这是设计选择。默认只推早评、真实模拟买入、真实模拟卖出、晚评。普通扫描和工程检查只保留在页面、CLI 或本地审计里，避免影响判断。

## 为什么有时候只有小仓验证？

收益守门会检查闭环样本、胜率、平均收益、回撤覆盖和赚撤比。样本质量没达标时，系统会降仓或空仓，避免把样例收益当真实稳定收益。

## 为什么预览文件不提交到 Git？

`client/desktop/preview/core_workflow.html` 是生成物，包含运行时状态和样例页面。开源仓库只保留源码和说明，预览页通过命令重新生成。

## 如何确认服务器没有重复实例？

Ubuntu 上执行：

```bash
cd /opt/firemoney
bash scripts/linux/check_firemoney_server.sh
```

Windows 本地执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_firemoney_runtime.ps1
```

## 能不能保证长期稳定赚钱？

不能保证。项目能做的是把策略规则、模拟盘执行、收益回撤和样本质量透明化，让不可靠的规则尽早暴露。任何真实交易都需要独立判断和风险控制。

## 腾讯云公网打不开怎么办？

优先用 SSH 隧道访问：

```powershell
ssh -N -L 8765:127.0.0.1:8765 -i $env:USERPROFILE\.ssh\firemoney_tencent -o IdentitiesOnly=yes ubuntu@81.70.202.132
```

然后打开：

```text
http://127.0.0.1:8765/core_workflow.html
```

如果必须公网访问，需要在腾讯云防火墙/安全组放行 `8765/tcp`。建议只放行自己的公网 IP，不要全网开放。
