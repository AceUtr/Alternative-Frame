# 本轮发布验证记录

- `pytest_output.txt` / `pytest_results.xml`：最终干净源码复测，218 项通过。
- `pytest_output_initial.txt` / `pytest_results_initial.xml`：修正前记录，217 通过、1 项 UTF-8 读取失败。
- `communication_result.json`：本轮确定性通信实验，5 Agent、每组 5 次；不含真实 LLM。
- `communication_example.txt`：实验终端输出，token 为字符估算。
- `manifest.json`：被检验源码、验证范围与文件哈希。

最终通过及通信记录按字节复制；两个 initial 文件仅统一 UTF-8、换行并去除行尾空白，原始与发布副本哈希在清单中分别保留，原件在发布者本地归档。本机绝对路径用于记录实际执行位置，在其他电脑上不应作为启动路径。后续复验使用各自独立的结果目录。源码分别记录实际测试字节和 Git 发布字节的哈希，CRLF/LF 行尾差异不视为源码逻辑变化。验收与使用说明见上级 `../../GITHUB_HANDOFF_20261111.md`。
