# 预览生成目录

本目录只保留说明文件。实际预览页和运行态文件由命令生成：

```powershell
python -B -m client.desktop.firemoney_client.preview
```

生成物包括：

- `core_workflow.html`
- `*.json`
- `*.sqlite3`
- `*.png`

这些文件可能包含本地运行状态、模拟盘样例或截图，不提交到 Git。
