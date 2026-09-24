# Evaluation Bundle

`evaluation` 用独立工作区和独立校验命令评估模型完成仓库任务的能力。

## 输入与输出

任务集由 JSON 描述：任务 ID、提示词、初始化文件、验证命令和验证超时。`EvaluationRunner` 为每个任务建立隔离目录，写入 fixture，运行 Agent，再执行 verify command，最终写出 `report.json`。

## 为什么需要独立验证

Agent 的最终文本不能证明代码正确；只有验证命令的退出码才决定 `passed`。评测层因此不采信模型自报结果。评测审批器只在一次性、可信的临时目录中自动批准工具，任务集本身包含可执行命令，运行前必须确认来源可信。
