# Artifacts Bundle

`artifacts` 从运行过程产生的工具事件中提取可展示的工程产物，不参与 Agent 决策。

## Git 变更

`WorkspaceChangeTracker` 在运行前后读取 Git 可见文件（含未跟踪文件），比较 SHA-256 和文本内容，生成新增/修改/删除、增删行数和 unified diff。`.minicode` 被排除；二进制或超过大小上限的文件只报告变化，不生成文本补丁。

## 测试结果

`extract_test_result()` 识别常见测试命令的 `run_shell` 事件，从输出中提取 passed/failed/skipped 计数，并结合退出码与超时状态生成 `TestResult`。这是启发式摘要，不替代测试框架自身的机器可读报告。
