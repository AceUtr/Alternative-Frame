# 答辩图表讲解要点

候选基线：`v1.1.0-competition-candidate`（commit `1d89c6023059`）；证据生成代码提交：`d19a5e1`。

## 多 Agent

单 Agent 平均耗时 `0.4027s`，多 Agent `0.3227s`，观察到 `1.248x` 加速；两组完成率均为 100%，每组重复 `5` 次。结论只限于该确定性工作负载的编排并行效果，不代表 LLM 推理质量提升。误差线是样本标准差。

## 局部恢复

Recovery OFF 最终完成：`False`；Recovery ON：`True`。恢复模式中 `prepare` 执行 `1` 次、局部恢复 `1` 次，说明前置成功步骤未重复执行。

## 契约验收

Contract OFF 完成判定：`True`；Contract ON：`False`，缺失项 `final_evidence`。被拦截代表正确拒绝虚报完成，不表示开启契约后该任务已经完成。

## 动态路由

固定云端完成：`False`；动态路由完成：`True`；最终节点 `edge`，回退 `1` 次。这是单机模拟运行时证据，不是多设备网络测试。

## 科研运行

两条科研样本的最终状态分别为 `True`、`True`；首次通过任务数分别为 `8`、`7`，恢复次数分别为 `0`、`1`。这是历史 `recorded_real_run`，不能称作本轮 API 实验或受控对照。

## API 实验状态

当前执行环境没有 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`，所以没有发送真实 API 请求。取得凭据后，先运行 API 诊断和低成本 smoke，再至少运行两次真实两阶段任务；API usage 缺失时保留 `unknown`。
