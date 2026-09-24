# Security Bundle

`security` 提供应用层安全边界：工作区路径解析和工具审批策略。它能降低 Agent 误操作风险，但不是操作系统沙箱。

## `Workspace`

`Workspace.resolve()` 将相对路径归一化为绝对路径，拒绝 `..` 逃逸、敏感凭据路径、Windows 保留设备名和 Alternate Data Streams。`.env.example` 等模板文件例外允许作为配置样例访问。

## `PermissionPolicy`

权限分为 `READ`、`WRITE`、`EXECUTE`。`ask` 交给调用方审批，`auto` 自动批准应用层允许的写入/执行，`read_only` 拒绝状态改变操作；高风险 Shell 模式即使在 `auto` 下也会拒绝。

## 威胁模型

路径保护只约束内置文件工具。Shell 仍以当前用户身份运行，可能访问工作区外资源，因此不应把 `auto` 描述成“完全访问”或“沙箱”。不可信代码需要 Docker、虚拟机或其他操作系统级隔离。
