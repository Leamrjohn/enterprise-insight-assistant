# 单机运行与故障恢复 Runbook

## 运行拓扑

单机由 PostgreSQL（平台数据与 pgvector）、Redis、Celery Worker、FastAPI 和模型 Provider 组成。任务事实来源是 `analysis_tasks`；消息仅由 Outbox 投递。不要通过 Redis 状态判断任务是否完成。

## 每次部署前

1. 执行 `docker compose config --quiet`。
2. 用项目 `.venv\Scripts\python.exe -m alembic heads` 确认单一 head。
3. 先处理历史数据完整性错误，再执行 `alembic upgrade head`；不得通过删除 RLS 或修改迁移绕过检查。
4. 启动 Postgres、Redis、API、Worker，并检查 `/health/live` 与 `/health/ready`。

## 任务卡住或失败

1. 在任务详情读取 `observability.latest_checkpoint`：查看 `completed_node`、`next_node`、`error_code` 与 `recovery_instruction`。
2. `running` 且 lease 过期：运行恢复器；只会把仍由过期 execution 持有的任务转为 `retrying`。不要手工把任意任务改为 `completed`。
3. `retrying`：确认 Outbox 事件是否已发布、Redis 是否可用、Worker 是否监听正确队列。
4. `model_budget_exhausted`：补充或调整下一次任务预算；当前任务不会无限 fallback。
5. `awaiting_review`：管理员通过审核接口批准或驳回。批准会新建 execution 并仅发布现有草稿；不会重跑模型。

## 依赖故障分类

- Embedding/向量检索故障：任务显示检索技术失败，可重试；不要将其写成“资料不足”。
- 无检索命中或充分性不足：返回 `insufficient_evidence` / partial；补充授权文档或范围。
- Provider 限流、网络与临时 5xx：受冻结 fallback 链和预算约束；检查 `model_usage` 与调用审计。
- Provider 鉴权、参数或结构契约错误：不重试、不 fallback；修复配置或 Prompt 契约后创建新任务。

## 数据与权限恢复

- 访问 pgvector 前必须在事务中设置 `SET LOCAL app.company_id`；缺失 scope 预期为零行。
- 文档撤销、成员离职或公司切换后，长期记忆读取应为空。不可用记忆不得通过手工复制进 Prompt 恢复。
- 备份前停止 Worker，备份 Postgres；恢复后先迁移、再验证 RLS 与只读经营账号，最后启动 Worker。

## 证明边界

单元和集成测试证明状态转换、权限和持久化。只有真实 Docker + Redis + Celery Worker + PostgreSQL 的端到端运行，才能证明消息投递、独立 Session 和 Worker 消费链路。
# 单节点运维 Runbook

## 可重复脚本

从仓库根目录运行：

```powershell
.\scripts\ops\verify-stack.ps1
.\scripts\ops\inspect-queue.ps1
$backupPassword = Read-Host "agent_backup password" -AsSecureString
.\scripts\ops\backup-postgres.ps1 -OutputDirectory "$env:TEMP\agent-platform-backups" -DatabasePassword $backupPassword
$restorePassword = Read-Host "agent_restore password" -AsSecureString
.\scripts\ops\restore-drill.ps1 -BackupPath "<dump path>" -DatabasePassword $restorePassword -Confirm:$false
```

恢复只能做演练：`restore-drill.ps1` 拒绝覆盖 `agent_platform` 与
`agent_platform_test`，并要求 PowerShell 的高影响确认。正式恢复必须先保留
现有备份、停止 Worker、由负责人确认目标库和恢复点。

恢复演练使用专用 `agent_restore`：它只有 `LOGIN + CREATEDB`，不具备超级用户、
创建角色或绕过 RLS 权限。老环境若在初始化前已创建数据卷，需要由现有数据库
管理员一次性创建该角色；不得把 API、Worker 或迁移账号提升为 CREATEDB。

业务库账号验证也从仓库根目录执行，参数必须连接实际业务数据库服务而不是平台库：

```powershell
$ownerPassword = Read-Host "business owner password" -AsSecureString
.\scripts\ops\verify-business-readonly.ps1 -DatabasePassword $ownerPassword -ReadonlyRole acme_readonly -Database acme_business -DatabaseService demo_business_acme
```

`agent_backup` 是唯一带 `BYPASSRLS` 的常规登录账号；它仅有只读导出权限，
不得配置给 API、Worker 或 Alembic。
