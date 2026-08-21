# Software Demo 录屏基准包

基准提交：`8638a1d`

## 启动

```powershell
cd "alternative-frame\v0.1"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python ui.py
```

## 录屏操作

1. 在任务模式下拉框选择 `Software Demo (offline)`。
2. 场景选择 `none`，先录制正常流程。
3. 点击“开始协作”。
4. 在合同预览窗口点击确认。
5. 展示任务表、DAG、验收证据、软件报告和产物路径。
6. 第二次可选择 `retry-once`，展示任务级重试证据。
7. 第三次可选择 `local-recovery`，展示局部恢复证据。

## 注意

- 这是离线软件 Demo，不需要 API Key。
- 不要从旧的 `alternative-frame\v0.1` 副本启动。
- 不要录入或展示 CCswitch 数据库、API Key 和个人路径。
- 录屏前确认窗口中的模式文字确实是 `Software Demo (offline)`。
