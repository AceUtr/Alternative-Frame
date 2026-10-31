# 比赛证据与 PPT 图表素材

图表由显式指定的结果文件生成，来源、配置、SHA-256 和候选 commit 记录在 `manifest.json`。生成器不会自动挑选最新文件。

- `agent_topology.png`：两种拓扑完成率均为 100%；本次确定性任务中多 Agent 平均耗时更低。
- `recovery_flow.png`：开启恢复后只重跑受影响的计算子图，准备步骤只执行一次。
- `contract_gate.png`：开启契约后，缺失最终证据的任务被正确拦截。
- `routing_fallback.png`：注入云端故障后，动态路由回退至边缘端成功；这是单机运行时模拟。
- `research_evidence.png`：历史科研运行证据，不是本轮 API 实验，也不是随机化对照。

`live_api_status=pending_credentials` 表示当前没有真实 API 结果；未检测到凭据时不会发送请求。
