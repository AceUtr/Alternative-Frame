# 受控 A/B 实验任务书：真实 API 下的有界依赖消息对照

## 1. 任务目的

本任务用于验证：在同一真实 API、同一任务和同一代码版本下，开启项目的“依赖消息传递”插件后，任务通过情况、通信量、API 请求量、用量和耗时是否发生变化。

本任务必须产生真实 API 运行记录，不能把确定性 Stub 或离线脚本结果写成真实模型证据。

## 2. 必须先理解的口径

之前 PPT 中的 `311 → 5` 来自确定性 5-Agent 脚本，不含真实 LLM 调用。旧实验的 OFF 组是脚本专门构造的“无界广播”压力基线；它不是本任务的 A 组。

本任务中的 A 组定义为：**依赖消息传递插件关闭，保留原有 DAG 执行路径**。

本任务中的 B 组定义为：**只开启依赖消息传递插件，使用有界消息总线投递依赖摘要**。

因此，A/B 结果不能直接解释为“无界广播 vs 有界广播”，也不能预期一定复现 98.4% 的下降。结果可能改善、基本不变或变差，都必须如实记录。

## 3. 交付边界

队员只负责运行和整理证据，不修改框架源码、插件实现、验收器或原始任务文本。若发现代码问题，停止实验并在报告中记录，不要在实验中途修代码。

实验只证明本次任务和本次 API 配置下的观察结果，不证明所有模型、所有任务或所有供应商都具有同样表现。

不得把 API Key 写入任务文本、截图、Markdown、JSON、CSV、日志、Git 提交或压缩包。

## 4. 队员开始前填写的固定信息

请在实验报告开头填写以下字段。API Key 只在 UI 窗口中输入，报告只写脱敏后的接口地址和模型名。

```text
experiment_id:
source_branch:
source_commit:
working_tree_clean: yes/no
project_root:
api_endpoint_redacted:
model:
temperature:
max_output_tokens:
global_token_limit:
max_model_calls:
max_runtime_seconds:
task_prompt_sha256:
contract_sha256:
operator:
start_time:
```

`source_commit` 必须是实际运行时的 commit。若工作区存在未提交的跟踪文件修改，不能声称是固定版本实验；应先停止并联系队长。

## 5. 实验任务

两组必须使用完全相同的下列任务文本。不要引用旧项目需求文档，也不要把历史聊天内容复制进任务框。

> 请在当前独立空工作区中完成一个可复现的 Python 科学计算器小项目，不修改 Alternative-Frame 框架源码，也不要读取或继承其他运行目录中的历史需求。创建 `calculator.py`，支持加、减、乘、除、平方根和幂运算；创建 `test_calculator.py`，覆盖正常输入、除零、负数开平方和非法输入；创建 `README.md` 说明运行方式；运行全部测试并在最终回复中给出实际测试命令、退出码、通过数、失败数和每个交付文件的相对路径。只有文件真实存在且测试命令退出码为 0 才算完成。

该任务足够小，用于控制 API 消耗；同时包含规划、实现、测试和验收依赖，可以观察依赖消息插件是否进入真实模型请求。不要自行扩大为科学计算平台、网页应用或跨领域研究任务。

## 6. 运行前统一条件

两组都必须满足以下条件：

- 同一个干净代码版本和同一个实际 commit；
- 同一个 API 接口地址、模型、温度、单次输出上限和全局预算；
- 同一份任务文本、同一份验收合同、同一工具集合；
- 每次使用全新的独立工作目录和新的 run ID；
- 不使用其他运行目录的记忆、产物、缓存或历史日志；
- 先完成 API 连接测试，再开始正式运行；连接测试不计入 A/B 样本；
- 运行期间不手工修改任务、合同、插件配置或产物；
- 失败、暂停、预算耗尽和人工干预都保留，不删除样本。

建议本次小任务使用如下预算，除非队长另有书面安排：

```text
单次输出上限：2048
全局 tokens：64000
模型调用上限：30
最长运行时间：600 秒
```

这些是客户端护栏，不是供应商账单上限。若供应商忽略输出限制，按运行记录如实报告。

## 7. 打开 UI 和填写模型

1. 在项目根目录双击 `启动长程任务UI.bat`，或在项目根目录运行 `python ui.py`。
2. “运行模式”选择 **API 模型**。
3. “接口地址”填写队长提供的 OpenAI-compatible Base URL。
4. “API Key”只粘贴到当前窗口，不写入文件。
5. “模型名称”填写服务商实际支持的模型 ID。
6. 填写统一预算，点击“测试连接”。只有连接成功后才开始正式样本。
7. 执行模式选择 **标准多 Agent**。如果队长明确要求长程任务，A/B 两组都必须选择长程任务，不能一组标准、一组长程。

## 8. A 组：依赖消息插件关闭

对每一次 A 组运行：

1. 点击“选择插件…”。
2. 点击“全部关闭”，确认主界面显示“全部关闭 · 保留原执行路径”。
3. 不勾选 BM25、依赖消息、执行队列、用量审计中的任何一项。这样只改变消息插件这一因素时，其他插件不会混入。
4. 使用独立空工作目录，粘贴第 5 节的任务文本。
5. 点击开始，检查合同预览中的目标、必需文件和测试命令；合同必须与 B 组一致后再确认。
6. 等待运行结束。不要重复点击开始，不要在任务运行期间切换插件。
7. 记录 run ID、状态、开始/结束时间和 UI 显示的结果路径。

注意：A 组的“关闭依赖消息”不等于旧脚本的“无界广播 OFF”。报告中必须使用“消息插件关闭”或“原 DAG 路径”这一名称。

## 9. B 组：只开启依赖消息插件

对每一次 B 组运行：

1. 新建一个独立空工作目录和新的 run ID。
2. API 配置、执行模式、预算、任务文本和验收合同必须与对应的 A 组相同。
3. 点击“选择插件…”，只勾选 **依赖消息传递**；BM25、执行队列和用量审计全部关闭。
4. 确认主界面摘要只显示“依赖消息”。
5. 开始运行并确认合同。运行期间不要切换插件或编辑任务。
6. 记录 run ID、状态、开始/结束时间和 UI 显示的结果路径。
7. 运行结束后检查协作日志中是否出现 `plugin_messages_delivered`。若没有该事件，B 组没有证明实际经过依赖消息插件，应标记为无效样本并联系队长。

## 10. 样本安排

正式结论至少需要 A 组 3 次、B 组 3 次完整尝试。建议交替运行，避免网络或服务商时段因素全部落在一组：

```text
A1 → B1 → A2 → B2 → A3 → B3
```

如果某次失败，保留该失败样本并继续补跑，使每组至少有 3 次实际尝试。报告中同时写“尝试数”和“通过数”，不能只保留成功样本。

首次可先做一轮 A1/B1 低成本试跑，检查消息事件是否正确，再决定是否继续完整 3+3 样本。低成本试跑不能单独用于最终 PPT 结论。

## 11. 每个运行必须保存的证据

长程任务通常位于：

```text
runs/long_horizon/<run_id>/
```

标准多 Agent 运行通常位于：

```text
runs/user_tasks/<run_id>/
```

每个样本完整保留对应 `<run_id>` 目录，至少包括：

- `state.json`：最终状态、阶段和失败原因；
- `events.jsonl`：控制器和任务事件；
- `api_usage.json`：累计请求、token、provider usage 或估算标记；
- `execution_metadata.json`：实际 commit、源码哈希、模型、预算和插件配置；
- `confirmed_contract.json`（长程任务）：运行时确认的验收合同；
- `plugins/config.json`：A/B 插件开关的事实记录；
- `plugins/audit/events.jsonl`：B 组的 `plugin_messages_delivered` 及其他插件审计事件；A 组也应保留该文件（若运行目录创建了插件目录）；
- 工作区中实际生成的源文件、测试文件、测试输出和报告；
- 运行结束后执行的独立文件清单和 SHA-256。

使用 `scripts/export_api_baseline.py --output <独立证据目录>` 可以导出脱敏的 API 基线摘要，但该导出不能替代原始运行目录。

## 12. 需要统计的指标

每个 run 单独填一行，不要只填均值：

```text
run_id
group (A_off / B_bounded)
repeat
commit
model
task_prompt_sha256
contract_sha256
controller_status
acceptance_passed
messages_delivered
message_chars_or_bytes
api_requests
provider_usage_total_tokens
estimated_total_tokens
usage_source (provider / local_estimate / unknown)
retry_count
recovery_count
wall_seconds
manual_interventions
state_path
events_path
api_usage_path
plugin_audit_path
artifact_manifest_path
```

消息数必须来自事件日志中的实际送达记录；不能根据模型回复内容猜测。若某项不存在，填写 `unknown`，不能填 0。

供应商没有返回 `usage` 时：

- `provider_usage_total_tokens` 填 `unknown`；
- 本地估算另填 `estimated_total_tokens`；
- `usage_source` 填 `local_estimate`；
- PPT 不得写成“真实 token 减少”。

## 13. 合同与来源一致性检查

在汇总前执行以下检查：

1. A/B 六次运行的实际 commit 相同；
2. A/B 六次运行的任务文本 SHA-256 相同；
3. A/B 六次运行的验收合同 SHA-256 相同；
4. A 组 `plugins/config.json` 中 `messages=false`；
5. B 组 `plugins/config.json` 中 `messages=true`，且其他三项为 false；
6. B 组每个有效样本都有 `plugin_messages_delivered` 事件；
7. 每个报告中的数字都能回溯到对应 JSON/JSONL；
8. JSON、CSV、Markdown 报告和图表引用同一批 run ID；
9. 运行目录中没有 API Key；
10. 失败和人工干预样本没有被删除或重标为成功。

任何一项不满足，都只能交付“实验未完成/证据不足”，不能生成提升百分比。

## 14. 汇总计算规则

先报告每次运行，再报告组统计。至少包括通过率、消息数均值/中位数、API 请求数、真实 usage 或未知比例、耗时和重试次数。

只有 A 组和 B 组使用完全相同的消息指标且 A 组平均消息数大于 0 时，才可以计算：

```text
message_reduction_pct = (A_messages_mean - B_messages_mean) / A_messages_mean × 100%
```

只有两组都拥有供应商真实 usage 时，才可以计算真实 token 差异。若一组或两组 usage 缺失，只报告“usage 未返回”，不要用估算值和真实值混算。

不要预设结果为 98.4%。真实 API 结果可能与确定性实验完全不同。

## 15. 交付物

队员最终提交一个新的证据目录，不覆盖旧的离线报告，目录建议如下：

```text
real_api_ab_<date>/
├─ EXPERIMENT_REPORT.md
├─ per_run_results.csv
├─ summary.json
├─ manifest.json
├─ A_off/
│  ├─ A1_<run_id>/
│  ├─ A2_<run_id>/
│  └─ A3_<run_id>/
├─ B_bounded/
│  ├─ B1_<run_id>/
│  ├─ B2_<run_id>/
│  └─ B3_<run_id>/
└─ charts/
   ├─ messages_ab.png
   ├─ requests_and_usage_ab.png
   └─ outcomes_ab.png
```

`EXPERIMENT_REPORT.md` 至少包含：实验目的、固定条件、每次运行明细、失败说明、A/B 统计、usage 来源、限制和结论。`manifest.json` 为每个关键文件记录相对路径、大小和 SHA-256。

图表标题应使用类似：

```text
真实 API 下依赖消息插件的受控 A/B 结果（n=3+3）
```

页脚写明模型、实际 commit、任务哈希、证据类型和原始数据文件。若样本不足或 usage 缺失，图表必须直接标注“探索性结果”或“usage unknown”。

## 16. 禁止事项

- 不把旧图的 `311→5` 改写成真实 API 数字；
- 不把 A 组称为“无界广播”；
- 不用一次成功运行声称普遍性能提升；
- 不混用 Stub、历史 API 运行和本次 A/B 运行；
- 不删除失败、暂停、预算耗尽或人工干预样本；
- 不将本地估算 token 写成供应商实际 usage；
- 不把 BM25、执行队列、用量审计同时开启后的结果归因于依赖消息插件；
- 不在实验中途修改源码或任务定义；
- 不把 API Key 交付给队长以外的人员或写入证据文件。

## 17. 队员回传前自检

- [ ] A 组至少 3 次、B 组至少 3 次尝试；
- [ ] 每次运行都有 run ID、commit、任务哈希和插件配置；
- [ ] B 组确实有 `plugin_messages_delivered` 事件；
- [ ] 失败样本全部保留；
- [ ] API usage 缺失已标记 `unknown` 或 `local_estimate`；
- [ ] 没有任何密钥进入文件；
- [ ] `summary.json`、CSV、报告和图表数字一致；
- [ ] manifest 中的 SHA-256 可复核；
- [ ] 已把完整证据目录和本报告一起交回。

## 18. 相关已有文件

- 离线通信原始报告：`E:/Project/WorkBuddy/Alternative-Frame-比赛/GitHub上传核对_20261111/clean_source/alternative-frame/v1.1-experimental/reports/noise-ablation/noise-ablation-20261111-102047.json`
- 离线图表及来源：`E:/Project/WorkBuddy/Alternative-Frame-比赛/补充证据图_20261110/图表数据与来源.json`
- 插件行为说明：项目 `docs/OPTIONAL_PLUGINS.md`
- 真实 API UI 流程：项目 `docs/真实API_UI操作流程.md`
- 项目开发待办：`E:/Project/WorkBuddy/Alternative-Frame-比赛/开发待办.md`（TODO-001）
发布补充说明：请先阅读同目录 API_AB_EXECUTION_NOTES.md。正式同合同实验请选择长程任务；A 组缺少插件事件不能记为零，不能据此计算消息减少率。
