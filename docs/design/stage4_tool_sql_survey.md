# 阶段 4.1：工具运行时与 SQL 防线调查（2026-11-02）

计划要求对照的教学版 `tool_layer.py` 在仓库中不存在，改为直接按 04/02 计划列出的契约项逐项检查。

## 工具运行时（`backend/app/modules/runtime/tool_runtime.py`）

| 契约项 | 现状 | 结论 |
|---|---|---|
| 注册 | 任务冻结的 `tool_policy_snapshot.allowed_tools` 白名单 + 运行时 schema 表（rag_search / sql_query / template_query） | 具备 |
| 参数校验 | Pydantic schema；未知工具 `tool_schema_unregistered`，校验失败 `tool_input_schema_invalid` | 具备；**多余参数被静默丢弃**而非拒绝（伪造的 `_runtime_timeout_ms` 会被丢弃再由服务端注入，安全） |
| 错误信息 | 所有拒绝都返回同一句“工具调用不在已授权范围内。”，错误码区分原因 | 对代码路由够用；4.5 让模型选工具时需要可指导修正的说明 |
| 超时 | 服务端注入 SQL `statement_timeout`、RAG 数据库超时 | 具备 |
| 截断 | SQL 自动补/收紧 LIMIT（默认 1000 行）；RAG top_k | 具备；SQL 文本与问题长度无上限 |
| 权限 | 每次调用重新校验当前授权、数据范围、文档范围 | 具备 |
| 审计 | 调用前后 workflow 事件 + ToolCallRecord，只记参数键不记参数值 | 具备 |
| 预算 | 每任务总调用数与单工具调用数上限，行锁预留 | 具备 |
| 幂等 | 无去重；靠预算限制重复调用 | 可接受 |

## SQL 五层防线

| 层 | 现状 | 本次发现 |
|---|---|---|
| 1 契约 | 只允许单条 SELECT | 具备 |
| 2 AST | 表白名单（公司快照 + 工具白名单），禁止 schema 前缀 | **27/54 种攻击可通过**：CTE 内 DELETE/UPDATE/INSERT、FOR UPDATE/SHARE、pg_sleep/pg_read_file/lo_import/set_config/dblink 等函数 → 已补（见 4.3） |
| 3 范围 | 经营库行级安全 + 公司快照 | 本次未改 |
| 4 执行 | 只读连接参数 + `SET TRANSACTION READ ONLY` + `statement_timeout` + 行数上限；分析账号 `acme_readonly` 非超级用户、不能绕过 RLS、0 个写权限、不能执行 pg_read_file/lo_import | 4.4 已自动化：`tests/integration/analysis/test_sql_execution_layer.py` 26 项，绕过 AST 后仍全部拦截；**模板查询路径以超级用户 business_app 连接且无只读事务**（待决定） |
| 5 审计 | 工具调用记录与事件 | SQL 原文不入审计（只在任务结果中） |
