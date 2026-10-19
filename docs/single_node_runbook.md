# 单机运行与故障恢复 Runbook

> 本文提供现有工具的操作入口，不代表恢复与运行治理已经验收。生产级要求见 [主路线图](single_node_production_style_ai_application_roadmap.md)，已验证/未验证范围见 [项目审计](project_core_audit_20260915.md)。

## 运行拓扑

单机环境由 FastAPI、平台 PostgreSQL/pgvector、Redis、Celery Worker、经营数据库、模型 Provider 和 React 前端组成。

- API、迁移、Beat 和 report-worker 使用不含 PyTorch 的 core 镜像。
- 默认 analysis worker 使用 CPU-only ML 镜像，负责当前代码中同步的 RAG embedding、rerank 和文档向量化。
- GPU embedding worker 不是把 `gpus: all` 加到通用 Worker 就能得到的能力；在内部 embedding 调用契约、超时与权限边界完成前，不启用它。
- 应用镜像固定以 UID/GID `10001` 的非登录用户运行。Linux 上若继续使用 `backend/logs`、`backend/storage` 这类 bind mount，宿主机必须预先授予该 UID 写权限；生产环境优先由受控卷或对象存储承载可写数据。

- PostgreSQL 中的任务记录是状态事实来源。
- Redis 只承担队列和短期协调，键数量不能代表 Celery 积压。
- Outbox 在数据库提交后发布任务消息。
- Worker 使用独立 Session，通过 `task_id` 恢复冻结的权限与证据范围。

## 启动前检查

从仓库根目录执行：

```powershell
Copy-Item backend/.env.example backend/.env
# 检查数据库密码、JWT_SECRET、模型 Provider 和 API Key。

docker compose config --quiet
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini heads
```

预期 Alembic 只有一个 head。新数据卷初始化时，Compose 会创建平台库角色和演示经营库；旧数据卷不会自动重新执行初始化脚本。

启动并检查：

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

`/health/ready` verifies PostgreSQL, Redis, and the configured object store. Any unavailable required dependency returns HTTP `503`; `live` only proves that the API process is answering.

If LocalStack alone is restarted, run its one-shot initializer again before treating the stack as ready:

```powershell
docker compose up -d --force-recreate localstack-init
.\scripts\ops\verify-stack.ps1
```

The initializer is responsible for creating the local development bucket. A LocalStack container being healthy does not prove that bucket exists.

## 任务卡住或失败

1. 从任务详情读取 `status`、`stage`、`attempt_count`、时间戳、`error_message` 和 `observability.latest_checkpoint`。
2. 同时核对 `completed_node`、`next_node`、`error_code`、`execution_id` 和租约时间；不要只根据单一状态判断。
3. 检查 Outbox 是否发布、Redis 是否可达、Worker 是否监听正确队列。
4. 检查 Worker 日志中的 `request_id`、`analysis_task_id`、`execution_id` 和失败节点。
5. 只对可重试错误恢复任务；不要手工把未发布报告的任务改为 `completed`。

常用脚本：

```powershell
.\scripts\ops\inspect-queue.ps1
.\scripts\ops\scan-orphaned-tasks.ps1
.\scripts\ops\verify-stack.ps1
```

## 常见故障分类

- Embedding 或向量服务失败：技术故障，可按错误分类重试；不能伪装为“资料不足”。
- 无检索命中或覆盖不足：业务证据不足，应补充授权文档或缩小问题范围。
- 模型限流、网络错误、临时 5xx：受冻结的 fallback 链、预算和重试上限约束。
- 模型鉴权、参数或结构契约错误：修复配置或 Prompt 契约后重新创建任务。
- SQL Schema、权限或 AST 校验失败：检查任务冻结的 Schema Snapshot 和只读账号，不得绕过校验器。
- `awaiting_review`：由授权人员批准或驳回；批准只发布已存在且通过校验的草稿。

## 队列检查

Redis 中的 key 数量不是队列积压。至少同时检查：

- Celery 队列的 `LLEN`。
- Worker 的 active、reserved 和 scheduled 任务。
- Worker 实际监听的队列名称。
- Outbox 中未发布、过期 `broker_accepted` 或发布失败的记录。

`inspect-queue.ps1` intentionally reports only these live Broker, Worker and durable-DB signals. Diagnose historical exceptions separately with a timestamp-bounded `docker compose logs` query; a raw log tail is not current queue health evidence.

当前本机保护边界为每公司最多 5 个、全局最多 20 个 `queued`/`running`/`retrying` 分析任务。超过边界的消息请求返回 HTTP `429` 和 `Retry-After`，同一事务中不会留下新的消息、任务或 Outbox 记录。可通过 `ANALYSIS_TASK_COMPANY_INFLIGHT_LIMIT`、`ANALYSIS_TASK_GLOBAL_INFLIGHT_LIMIT` 和 `ANALYSIS_TASK_ADMISSION_RETRY_AFTER_SECONDS` 配置；这些是保守的防堆积阈值，尚不是测得的客户容量或 SLO。

`inspect-queue.ps1` 同时输出在途总数、按公司在途数和最老待处理任务等待秒数。Celery 的 Redis 队列本身没有设置 `max_length`；因此必须以任务 admission 限额而不是 Redis key 数量判断是否已受控。

每个 Compose 服务使用 Docker `json-file` 日志轮转，最多保留 3 个 10 MiB 文件。API 与 Worker 的 PostgreSQL Session pool 默认是 `size=5`、`max_overflow=10`、`timeout=5s`；`DATABASE_POOL_SIZE` 必须为正，`DATABASE_MAX_OVERFLOW` 不得为负，超出连接池边界应在超时后失败而非无限等待。

## 数据、权限与恢复

- pgvector 查询前必须在事务中设置公司作用域；缺少 scope 时预期不返回租户数据。
- 文档撤销、成员禁用或公司范围变化后，不得从旧 Prompt 或缓存恢复已失效权限。
- 经营数据库账号必须保持只读，并只授予允许的表和 Schema。
- 正式恢复前停止 Worker、确认恢复点并保留现有备份。

备份和恢复演练：

```powershell
$backupPassword = Read-Host "agent_backup password" -AsSecureString
.\scripts\ops\backup-postgres.ps1 -OutputDirectory "$env:TEMP\agent-platform-backups" -DatabasePassword $backupPassword

$restorePassword = Read-Host "agent_restore password" -AsSecureString
.\scripts\ops\restore-drill.ps1 -BackupPath "<dump path>" -DatabasePassword $restorePassword -Confirm:$false
```

备份会同时生成不可变清单（dump 的 SHA-256、大小、Alembic 版本、public 表数和关键执行/审计/账本表行数）。恢复演练会先校验清单和 dump 哈希，再在隔离数据库比对这些值；默认本地演练门禁为备份年龄（RPO）不超过 15 分钟、恢复耗时（RTO）不超过 900 秒。它们是本机演练目标，不是生产 SLA。

该 PostgreSQL 演练尚不能单独证明对象存储原件、向量索引、撤回/删除水位、角色权限或报告引用一致性；完整验收须补主路线图 M4/P6-3 的检查。

`restore-drill.ps1` 拒绝覆盖 `agent_platform` 和 `agent_platform_test`。正式恢复需要单独确认目标数据库、恢复时间点、停机范围和回滚方案。

验证经营库只读账号：

```powershell
$ownerPassword = Read-Host "business owner password" -AsSecureString
.\scripts\ops\verify-business-readonly.ps1 -DatabasePassword $ownerPassword -ReadonlyRole acme_readonly -Database acme_business -DatabaseService demo_business_acme
```

## 验证边界

- 单元测试：证明纯函数、Schema、路由决策和局部错误处理。
- 集成测试：证明应用依赖、数据库持久化、权限和事务边界。
- 真实 Worker E2E：只有测试实际经过的 Redis、Worker、经营库、检索、模型和持久化环节才有证明力；取消任务或模型调用测试不能代替完整经营分析 E2E。
- 业务评测：单独证明检索、引用、数字、拒答和报告质量；不能用“测试数量”替代。
