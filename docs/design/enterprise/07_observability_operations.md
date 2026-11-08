# 可观测和运维实现设计

**状态：** 设计稿，未实现。文中配置和代码是草案。对应总计划工单 O1～O7、B11～B13。

**不变的约束：** 遥测不记录问题原文、回答、文档内容和 SQL 结果；密钥不进日志。

---

## 1. 现在怎么运行

| 能力 | 现状 | 依据 |
|---|---|---|
| 日志 | 一行 JSON，字段白名单，统一脱敏，带 `request_id`、`task_id` | `core/logging.py:30-94` |
| 任务轨迹 | 每步写 `workflow_events`，脚本渲染静态页面 | `render_task_trace.py` |
| 账本 | 每次模型和工具调用都有记录 | `model_call_records`、`tool_call_records` |
| 指标 | 只有一个 API `/observability/task-metrics` | `observability/api.py:13` |
| 健康检查 | `/health/live`、`/health/ready` 查数据库、Redis、存储、容量 | `health_service.py:10` |
| 容器探活 | `postgres`、`redis` 等有；`api`、`worker`、`beat` 没有 | `docker-compose.yml` |
| 运维 | Runbook、备份和恢复演练、孤儿扫描、容量测量、故障演练 | `docs/operations/`、`scripts/ops/` |
| 告警、SLO、跨进程 Trace | 没有 | 代码中未见 OpenTelemetry、Prometheus |

**要保留的好设计：** 日志字段白名单（比黑名单安全）；事件带序号；演练脚本用真实故障；`restore-drill.ps1` 有时限和清单校验。

**实际缺口：**

| 问题 | 后果 |
|---|---|
| 没人会主动告诉你出事了 | 只有用户发现或人工查看才知道 |
| 聚合数字要写 SQL | 看不到成功率、P95、费用趋势 |
| 无法跨 API、Celery、Worker 串联 | 能看任务事件，但看不到排队时间等 |
| `restart: unless-stopped` 不处理“卡死” | 容器活着但不工作时，Docker **不会**重启它 |
| 恢复投递有疑点 | 见第 6 节 |

---

## 2. 组件选择

```text
API / Worker / Beat ──OTLP──→ OTel Collector ──→ Prometheus（指标）──→ Grafana
                                            └─→ Tempo（Trace）   ──→ Grafana
指标导出器（读数据库）──────────────────────→ Prometheus ──→ Alertmanager ──→ 通知
```

**选这套的理由：** 都是常用开源组件，单机能跑。Celery 是多进程，用 OTLP 推送比进程内暴露指标更简单。

| 容器 | 作用 | 备注 |
|---|---|---|
| `agent-otel-collector` | 接收、过滤、转发 | 这里再过滤一次敏感属性 |
| `agent-prometheus` | 指标存储、告警规则 | 保留 30 天 |
| `agent-tempo` | Trace 存储 | 保留 7 天 |
| `agent-grafana` | 看板 | 只绑定 `127.0.0.1`，看板配置进版本库 |
| `agent-alertmanager` | 告警路由 | |
| `agent-metrics-exporter` | 把数据库状态转成指标 | 只读，用控制面角色 |

全部放在 compose 的 `observability` profile，不影响现有启动方式。**这些都是新依赖和新容器，需要批准。** 镜像版本要固定。

**先做轻量版也可以：** 只上指标导出器、Prometheus、Grafana、Alertmanager，不需要改应用代码。这是 O2 的第一步，可以很快看到效果。

---

## 3. 全链路 Trace（O1）

### 3.1 怎么把链路串起来

```text
API 中间件      开 span "POST /conversations/{id}/messages"
建任务          把 traceparent 写进 analysis_tasks.trace_context 和 Outbox payload
Beat 发布       继续 trace，传给 Celery header
Worker 认领     恢复上下文，开 span "analysis_task"，记录排队时长
节点包装        graph.add_node 时统一包一层 span，不改节点逻辑
工具流水线      span "tool.sql_query"（第 13 步写审计时一并结束）
模型路由器      span "gen_ai.chat"，每次物理调用一个
崩溃恢复        新尝试用同一 trace_id，新 span 标记 resumed=true
```

### 3.2 属性白名单

| 允许 | 禁止 |
|---|---|
| `task_id`、`execution_id`、`node`、`tool.name`、`tool.version`、`error.class` | 问题、回答、SQL、文档内容 |
| `gen_ai.request.model`、token 数、`finish_reason` | 提示词全文、工具参数值 |
| `company_id`（只在 Trace，不进指标标签） | 用户姓名、用户名 |

**两道过滤：** 代码封装 `safe_span_attributes()`，只接受白名单键；Collector 再配置一次。

### 3.3 和现有事件的关系

`workflow_events` 和账本**继续是事实来源**（有事务保证）。Trace 用于看时间线，丢失不影响业务。Tempo 挂掉时只写警告，任务继续。

---

## 4. 指标（O2）

**标签不能放 `task_id`、`user_id`、`company_id`，否则时间序列会爆炸。** 需要按公司看时，由导出器定期聚合前 N 家，或直接查账本。

| 指标 | 类型 | 标签 | 来源 |
|---|---|---|---|
| `agent_tasks_total` | 计数 | `status` | Worker 终态 |
| `agent_task_duration_seconds` | 直方图 | `route`、`status` | Worker |
| `agent_task_queue_seconds` | 直方图 | | Worker 认领时 |
| `agent_node_duration_seconds` | 直方图 | `node` | 节点包装 |
| `agent_model_calls_total` | 计数 | `purpose`、`model`、`error_kind` | 路由器 |
| `agent_model_tokens_total` | 计数 | `purpose`、`direction` | 路由器 |
| `agent_model_cost_total` | 计数 | `purpose` | 结算 |
| `agent_model_unknown_cost_calls_total` | 计数 | `error_kind` | 结算 |
| `agent_tool_calls_total` | 计数 | `tool`、`error_class` | 流水线 |
| `agent_breaker_state` | 仪表 | `name` | 熔断 |
| `agent_context_over_budget_total` | 计数 | `node`、`action` | 引擎 |
| `agent_validation_failures_total` | 计数 | `check` | 校验 |
| `agent_memory_selected` | 直方图 | | 记忆 |
| `agent_http_requests_total` | 计数 | `route`、`status` | 中间件（用路由模板，不用真实路径） |

**指标导出器（每 30 秒查一次数据库）：**

| 指标 | SQL 含义 |
|---|---|
| `agent_tasks_inflight` | 按状态统计进行中的任务 |
| `agent_outbox_pending_age_seconds` | 最老未发布事件的年龄 |
| `agent_leases_expired` | 已过期但未回收的租约数 |
| `agent_tasks_stranded` | `retrying` 且长时间没有进度的任务 |
| `agent_reserved_billing_stale` | 长时间停留在 `reserved` 的账本记录 |
| `agent_beat_last_run_age_seconds` | Beat 任务上次运行距今多久 |

---

## 5. SLO 和告警（O3）

**没有真实流量，SLO 只能先用自测数据。** 下面都是初值，要用基线校准；不能声称已满足线上 SLO。

| SLI | 初始目标 | 窗口 |
|---|---|---|
| 任务正常结束率（非 `failed`） | ≥ 99% | 7 天 |
| 数据类任务 P95 耗时 | ≤ 基线 1.5 倍 | 7 天 |
| API 可用性（`/health/ready`） | ≥ 99.5% | 7 天 |
| 单任务费用 P95 | ≤ 基线 1.5 倍 | 7 天 |
| 跨公司泄漏、写经营库、绕过校验发布 | **0**（硬门禁） | 永远 |

| 告警 | 条件 | 级别 | 第一步动作 |
|---|---|---|---|
| WorkerDown | 5 分钟无 Worker 指标 | 严重 | `scripts/ops/status.ps1`，看 `agent-worker-1` 日志尾部 |
| BeatStalled | Beat 上次运行超过 2 分钟 | 严重 | 看 `agent-beat-1` |
| QueueBacklog | 最老事件超过 5 分钟 | 高 | `inspect-queue.ps1` |
| TasksStranded | 卡住任务 > 0，持续 10 分钟 | 高 | `scan-orphaned-tasks.ps1` |
| ModelErrorSpike | 模型错误率 > 20%，5 分钟 | 高 | 按 `error_kind` 查，是否供应商故障 |
| BreakerOpen | 熔断打开超过 5 分钟 | 高 | 查对应依赖 |
| UnknownCostSpike | 未知费用 > 5 次/小时 | 中 | 查超时和租约过期 |
| CostBurn | 小时费用超过基线 3 倍 | 高 | 按用途查，必要时用紧急开关 |
| ValidationFailSpike | 校验失败率翻倍 | 中 | 可能是提示词或模型变化 |
| BackupStale | 最新备份超过 26 小时 | 高 | 跑备份脚本 |
| DiskLow | 磁盘低于水位 | 高 | 现有容量信号 |

**通知渠道要你决定：** 本机可以先写到本地文件并在 Grafana 显示。发到企业微信、邮件等要配置外部地址。

**每条告警都写进 Runbook：** 现象、影响、第一步、如何确认恢复。没有处理步骤的告警不上线。

---

## 6. 卡死恢复和孤儿任务（O4、B11、B12）

### 6.1 容器探活

**Docker 的重启策略不处理 unhealthy。** 只配 `healthcheck` 不够，所以用“自我退出”：

| 容器 | 探活 | 卡死后怎样 |
|---|---|---|
| `api` | `/health/live`（不查依赖，否则依赖故障会连带重启） | 配合 `autoheal` 或由 Worker 的同款看门狗退出 |
| `worker` | Celery 主进程每 30 秒写心跳文件；看门狗线程检查 | 超过阈值，进程退出 → `restart` 重启 → 租约过期后任务恢复 |
| `beat` | 每次任务写时间戳 | 同上 |

**不要用 `celery inspect ping` 做探活：** 执行长任务或 Redis 抖动时会误判。

### 6.2 恢复投递修复（B11）

现状（`outbox_tasks.py:35-39`）：

```python
task_ids = recover_expired_executions(db)   # 已提交：任务变 retrying
for task_id in task_ids:
    process_analysis_task.delay(task_id=task_id)   # 这里失败就没人再投递
```

**先写失败测试复现，再修。** 目标：

```python
for task_id in task_ids:
    try:
        process_analysis_task.delay(task_id=task_id)
    except Exception:
        logger.warning(...)     # 单个失败不影响同批其他任务
```

**再加一个兜底（B12）：** Beat 每分钟运行 `reconcile_stranded_tasks`：

```sql
SELECT id FROM analysis_tasks
WHERE status = 'retrying'
  AND active_execution_id IS NULL
  AND updated_at < now() - interval '2 minutes'
LIMIT 50;
```

重新投递。重复投递是安全的，因为认领是原子条件更新（`execution.py:286`）。`updated_at` 字段存在（`workflow/models.py:183`），但每次状态迁移是否都会更新它，开工时要先确认。

**死信：** 超过 `MAX_DELIVERY_ATTEMPTS` 的任务转 `failed`，错误码 `delivery_exhausted`，并告警。不无限投递，也不静默丢弃。

### 6.3 并发和容量（B13、O7）

**现在 `--concurrency=1`。提高前要满足：**

| 前提 | 为什么 | 对应 |
|---|---|---|
| 模型网关不改写状态 | 防止串模型 | G2 |
| 上下文变量按任务隔离 | `ContextVar` 在进程内可用，线程池要确认 | 测试 |
| 数据库连接池够用 | 每个 Worker 进程一个池 | 配置 |
| 嵌入和重排模型内存够 | 每个进程都加载一份模型 | 测量 |
| 提前查出死锁 | 已发生过一次 | 并发测试 |

**容量测试（不花钱）：** 用脚本化假模型（延迟可配）跑阶梯压力 1 → 5 → 10 → 20 个任务，复用 `measure-agent-capacity.ps1`，记录吞吐、P95、队列、内存和错误。**输出容量报告，据此设置 `analysis_task_global_inflight_limit`。**

**长时间运行（soak）：** 6 小时持续低压，观察内存增长、连接数和任务卡住情况。

---

## 7. 备份、恢复和演练（O5、O6）

| 目标 | 设计 |
|---|---|
| 备份频率 | 每天 1 次全量（`backup-postgres.ps1`），由系统计划任务触发 |
| RPO（最多丢多久数据） | 初值 24 小时；要更短需要 WAL 归档，属于上线级 |
| RTO（多久恢复） | 用 `restore-drill.ps1` 实测后再写目标 |
| 恢复校验 | 表行数、迁移版本、抽样任务可读、RLS 仍生效 |
| 恢复频率 | 每月一次，结果写进 `docs/operations/drills/` |

**不要恢复到正在使用的库。** 演练用独立临时容器，名称以 `agent-` 开头。**绝不使用 `docker compose down -v` 或删除数据卷。**

**故障演练表（每季度，或大改之后）：**

| 演练 | 注入方式 | 通过标准 |
|---|---|---|
| Worker 崩溃 | 杀进程 | 任务恢复，结果不重复 |
| 旧 Worker 复活 | 暂停后恢复进程 | 写入被拒绝 |
| Redis 中断 | 停容器 | API 明确失败；恢复后任务继续；**无卡死任务** |
| Redis 在恢复时中断 | 注入 `delay` 失败 | 兜底任务重新投递 |
| 数据库中断 | 停容器 | 明确失败，恢复后继续 |
| 经营库中断 | 停演示库 | 熔断生效，另一公司不受影响 |
| 模型供应商故障 | 假供应商 | 重试、备用、明确失败 |
| 用户取消 | 运行中取消 | 取消后不写结果 |
| 迁移失败 | 故意失败的迁移 | 不影响运行中的旧版本 |
| 发布回滚 | 部署后回滚 | 回到上一版本且功能正常 |

现有 `stage3_5_game_day_plan.md` 的演练项保留并合并进来。这些演练**只操作 `agent-` 开头的容器**。

---

## 8. 配置

| 配置项 | 默认值 |
|---|---|
| `OTEL_ENABLED` | `false` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 本地 Collector |
| `OTEL_SAMPLING_RATIO` | 1.0（本机） |
| `WORKER_WATCHDOG_STALE_SECONDS` | 180 |
| `STRANDED_TASK_AFTER_SECONDS` | 120 |
| `MAX_DELIVERY_ATTEMPTS` | 5 |

---

## 9. 落地步骤

**验证命令是计划，尚未运行。** 新依赖和新容器都要先批准。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B11 恢复投递** | `outbox_tasks.py`；先写注入 `delay` 失败的测试 | 测试先失败后通过；同批其他任务照常投递 | revert |
| **B12 兜底和死信** | `reconcile_stranded_tasks`；`celery_app.py` 调度 | 模拟卡住任务被重新投递；超次数转失败 | 关调度 |
| **O4 探活** | compose、看门狗 | 模拟卡死后自动重启，任务恢复 | 去掉配置 |
| **O2a 看板（轻量）** | 指标导出器、Prometheus、Grafana、compose profile | 看板显示第 4 节导出器指标 | 不启动 profile |
| **O3 告警** | 规则文件、Runbook | **逐条注入故障**，5 分钟内告警 | 关规则 |
| **O1 Trace** | `core/telemetry.py`、中间件、任务传播、节点包装（**改表：`trace_context`**） | 一个任务能看到 API 到模型的完整链路；白名单测试 | `OTEL_ENABLED=false` |
| **O2b 应用指标** | 流水线、路由器、引擎埋点 | 指标数值和账本对得上 | 关闭 |
| **O5 演练** | `scripts/ops/drills/`，每项一个脚本 | 第 7 节全表通过，结果入库 | 无 |
| **O6 备份恢复** | 计划任务、恢复校验 | 实测 RPO、RTO 写入文档 | 无 |
| **O7、B13 容量和并发** | 假模型压力脚本；并发配置 | 容量报告；并发 > 1 演练通过 | 改回 1 |

**建议顺序：** B11 → B12 → O2a → O4 → O3 → O1 → O2b → 其余。B11 最小且修的是已知问题，O2a 不用改应用代码。

---

## 10. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 杀 Worker | 5 分钟内告警，自动恢复，任务完成 |
| 注入 `delay` 失败 | 没有任务永远卡住 |
| 任选失败任务 | 5 分钟内说出失败在哪一步（路线图原目标） |
| 指标对账 | Prometheus 费用和账本差异在允许范围内 |
| 敏感扫描 | Trace、日志、指标中 0 命中 |
| 关掉整套观测 | 任务照常运行 |
| 恢复演练 | 有实测 RPO、RTO 和校验结果 |

**仍需开工时确认：** `inspect-queue.ps1` 等脚本的准确用法；Tempo 和 Prometheus 在这台电脑上的内存占用是否可接受（不够就先不上 Tempo）；通知渠道。
