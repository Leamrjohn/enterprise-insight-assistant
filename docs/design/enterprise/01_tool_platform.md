# 工具平台实现设计

**状态：** 设计稿，未实现。文中代码是接口草案，不是已有代码。对应总计划工单 T1～T9。

**不变的约束：** 模型只能提议；权限、范围、SQL 校验由代码决定；经营库只读；主链结构不变。

---

## 1. 现在怎么运行

以主链查询销售额为例（`model_tool_mode=off`，也就是默认路径）：

```text
tasks.py:635   Worker 创建 ToolRuntime(db, attempt, context)，放进工作流状态
nodes.py:591   data_node 创建 DataAgent(sql_tool=runtime.wrap(SQLTool(...)))
data_agent.py:304  self._sql_tool.execute(ToolInput({"sql": candidate.sql}))
tool_runtime.py:81  RuntimeTool.execute → ToolRuntime.execute
tool_runtime.py:371 依次：白名单 → 当前权限 → 参数 → 范围 → 文档权限 → 预算
tool_runtime.py:407 tool.execute(input)  → SQLTool → validate_sql → execute_readonly_sql
tool_runtime.py:428 写 workflow_event 和 tool_call_records
```

**这条路径的优点：** 所有工具都过 `ToolRuntime`，权限每次重新校验。

**它的问题：**

| 问题 | 实际后果 |
|---|---|
| 工具信息分散在 3 张字典（`:32`、`:147`、`:302`）和 `ToolSpec` | 新增工具至少改 4 处，漏一处就不一致 |
| 只有工具模式才走 `GuardedTool`（`nodes.py:579`），主链直连 `SQLTool` | 经营库故障时，主链每个任务都要等到超时 |
| `GuardedTool` 包在 `ToolRuntime` 内层 | 重试 1 次执行 2 遍，审计只有 1 条 |
| 失败分类靠错误码集合推断（`tool_guard.py:22`、`:36`），空错误码当基础设施故障（`:52`） | 新错误码默认归类可能是错的 |
| 模型工具（`run_sql`）和运行时工具（`sql_query`）没有映射表 | 看不出模型的一次调用对应了什么实际执行 |

---

## 2. 目标结构

```text
backend/app/modules/runtime/tools/
    definition.py   ToolDefinition、RetryPolicy、BreakerPolicy、ErrorClass
    registry.py     ToolRegistry：加载、校验、计算目录哈希
    catalog.py      所有工具在这里声明（唯一来源）
    errors.py       错误码 → ErrorClass 对照表
    pipeline.py     ToolPipeline：固定顺序的执行流水线
    audit.py        写 tool_call_records 和事件
    results.py      ToolResultStore：大结果句柄（T8 才启用）
```

`tool_runtime.py` 保留 `ToolRuntime`、`RuntimeTool` 这两个名字，内部改为调用流水线。这样 `DataAgent`、`KnowledgeAgent` 不用改。

### 2.1 工具定义

```python
class ErrorClass(StrEnum):
    CALLER = "caller_error"      # 调用方的错：退回模型修正
    DENIED = "denied"            # 权限或范围：立即停止，绝不重试
    INFRA = "infra_error"        # 依赖故障：重试、计入熔断
    EXHAUSTED = "exhausted"      # 配额用完：结束本次循环
    TASK_STOP = "task_stop"      # 取消或模型预算耗尽：向上抛

@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 0         # 主链默认不重试，由定义显式打开
    backoff_ms: int = 500
    jitter: float = 0.2

@dataclass(frozen=True)
class BreakerPolicy:
    enabled: bool = True
    scope: Literal["global", "company"] = "global"
    threshold: int = 5
    window_s: int = 60
    cooldown_s: int = 30

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str                 # 语义版本；改输入或输出契约时要升
    owner: str
    kind: Literal["runtime", "capability", "control"]
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None
    side_effect: Literal["read", "write"]
    allowed_roles: frozenset[str]
    scope_binder: Callable[[ToolInput, ToolCallContext], ToolInput | ScopeDenied]
    timeout_ms: int
    timeout_mechanism: Literal["db_statement", "http_client", "subprocess", "none"]
    retry: RetryPolicy
    breaker: BreakerPolicy
    max_result_tokens: int
    on_overflow: Literal["reject", "truncate_rows", "handle"]
    backed_by: str | None = None # capability 指向的 runtime 工具
```

**三种工具（解决“两套工具”的问题）：**

| kind | 例子 | 是否真正执行 | 是否进流水线 |
|---|---|---|---|
| `runtime` | `sql_query`、`rag_search`、`template_query` | 是 | 是 |
| `capability` | `run_sql` → `sql_query`；`search_documents` → `rag_search`；`describe_table` | 模型可见，实际执行走 `backed_by` | `backed_by` 的部分进 |
| `control` | `submit_result`、`submit_answer`、`report_no_evidence` | 否，只结束循环 | 否，但要校验参数并记录 |

### 2.2 目录声明示例

```python
SQL_QUERY = ToolDefinition(
    name="sql_query", version="2.0.0", owner="data", kind="runtime",
    description="执行通过校验的只读 SQL。",
    input_model=SQLQueryInputSchema, output_model=SQLQueryOutput,
    side_effect="read", allowed_roles=ANALYSIS_ROLES,
    scope_binder=require_task_company,
    timeout_ms=10_000, timeout_mechanism="db_statement",
    retry=RetryPolicy(max_retries=1),
    breaker=BreakerPolicy(scope="company"),  # 一家公司的库坏了不影响别家
    max_result_tokens=2_000, on_overflow="truncate_rows",
)
```

### 2.3 注册表启动校验

`ToolRegistry.build()` 在 API 和 Worker 启动时运行，任一条不满足就**启动失败**：

1. 名称唯一，版本符合语义版本。
2. `side_effect="write"` 一律拒绝（当前不开放写操作）。
3. `kind="capability"` 的 `backed_by` 必须存在且是 `runtime`。
4. `timeout_mechanism="none"` 只允许不访问外部资源的工具。
5. 每个 `runtime` 工具必须声明允许的角色和范围绑定。
6. 计算 `catalog_hash`（名称、版本、输入 Schema 的哈希），写入任务快照和审计。

---

## 3. 目标运行流程

流水线替换 `ToolRuntime.execute`。**顺序固定，单个工具不能改顺序或跳过。**

| # | 阶段 | 做什么 | 失败时 |
|---|---|---|---|
| 1 | 登记 | 从注册表取定义 | `tool_not_registered`，DENIED |
| 2 | 策略 | 任务快照的 `allowed_tools` 是否包含它 | `tool_not_allowlisted`，DENIED |
| 3 | 取消检查 | 任务是否已取消 | 抛 `ToolCallCancelled`，TASK_STOP |
| 4 | 当前权限 | 用户启用、成员已批准、角色匹配 | `tool_current_authorization_denied` |
| 5 | 参数校验 | 用 `input_model` 校验 | `tool_input_schema_invalid`，CALLER |
| 6 | 范围绑定 | `scope_binder` 覆盖公司和文档范围 | `tool_*_scope_denied`，DENIED |
| 7 | 服务端参数 | 加超时等；模型不能传带 `_runtime_` 前缀的参数 | 不会失败 |
| 8 | 配额预占 | 带行锁扣减任务工具预算 | `tool_budget_exhausted`，EXHAUSTED |
| 9 | 熔断判断 | 打开时快速失败，半开时放一个探测 | `tool_circuit_open`，INFRA |
| 10 | 执行 | 带超时执行；INFRA 且策略允许时退避重试 | 分类后进入第 13 步 |
| 11 | 结果校验 | 用 `output_model` 校验 | `tool_output_contract_invalid`，INFRA |
| 12 | 大小控制 | 超过 `max_result_tokens` 时按 `on_overflow` 处理 | 按策略拒绝或截断并标记 |
| 13 | 审计 | **每次实际执行**写一条记录 | 见第 5 节 |

### 3.1 一次调用的具体过程

用户问“华东区 2025 年 8 月已交付订单销售额”，`DataAgent` 生成了 SQL，第一次连接失败，第二次成功：

```text
logical_call_id = 7f3a…（一次逻辑调用只有一个）

1～7  通过，公司 12，角色 analyst
8     任务 tool_budget_usage: calls 2 → 3（只扣 1 次，重试不再扣）
9     breaker key=tool-circuit:sql_query:12，状态 closed
10.1  attempt_no=1 → business_db_execution_failed → INFRA
      写审计 status=failed error_class=infra_error duration_ms=312
      等 500ms × 抖动
10.2  attempt_no=2 → 返回 1 行
      写审计 status=succeeded duration_ms=48
11～12 校验通过，结果 40 token，未超限
      breaker.record_success()
```

`tool_call_records` 里出现两条记录，排查时能看到“实际执行了 2 次，逻辑上 1 次”：

| logical_call_id | attempt_no | status | error_class | duration_ms |
|---|---|---|---|---|
| 7f3a… | 1 | failed | infra_error | 312 |
| 7f3a… | 2 | succeeded | | 48 |

### 3.2 超时怎么实现

**不用线程强杀。** Python 杀不掉正在执行的线程，强杀还可能破坏数据库会话。每种机制由工具自身保证，再由注册表校验已声明：

| 机制 | 实现 | 已有基础 |
|---|---|---|
| `db_statement` | `statement_timeout` | `sql_executor.py`、`rag_database_timeout_ms` |
| `http_client` | 客户端超时参数 | `llm_timeout_seconds` |
| `subprocess` | 超时后结束子进程 | MCP stdio 需要补 |

流水线另外检查实际耗时。超过 `timeout_ms` 的 1.5 倍时，写 `tool_timeout_overrun` 事件告警，因为这说明工具的超时没有生效。

### 3.3 错误分类对照表（`errors.py`）

| 错误码 | 分类 |
|---|---|
| `tool_not_allowlisted`、`tool_*_scope_*`、`tool_current_authorization_denied` | DENIED |
| `tool_input_schema_invalid`、`sql_validation_error`、`sql_input_missing`、`sql_statement_timeout`、`rag_validity_window_invalid`、`template_query_invalid_request` | CALLER |
| `business_db_execution_failed`、`mcp_transport_unavailable`、`local_embedding_failed`、`local_rerank_failed`、`template_query_execution_failed`、`tool_runtime_unexpected_error` | INFRA |
| `sql_timeout_policy_invalid`、`rag_timeout_policy_invalid`、`template_query_not_implemented` | INFRA（配置或实现问题，不应由模型修正） |
| `tool_budget_exhausted` | EXHAUSTED |
| `model_budget_exhausted`、`task_cancelled` | TASK_STOP |

`sql_statement_timeout` 归 CALLER，与现有判断一致（`tool_guard.py:54`）：超时通常是语句本身的问题。

**未登记的错误码按 INFRA 处理并写告警事件，CI 测试要求全部错误码都已登记。**

**RAG 要补错误码：** `knowledge/tool.py:67`、`:267`、`:277` 现在返回失败时没有错误码。建议新增 `rag_input_missing`（CALLER）、`rag_search_unavailable`（INFRA）、`rag_retrieval_failed`（INFRA）。

---

## 4. 数据结构改动

只新增字段，不改旧字段。历史记录的新字段保持空值，`logical_call_id` 不回填。

```sql
ALTER TABLE tool_call_records
  ADD COLUMN logical_call_id uuid,
  ADD COLUMN attempt_no      integer NOT NULL DEFAULT 1,
  ADD COLUMN error_class     varchar(16),
  ADD COLUMN tool_version    varchar(32),
  ADD COLUMN catalog_hash    varchar(64),
  ADD COLUMN result_tokens   integer,
  ADD COLUMN result_truncated boolean NOT NULL DEFAULT false;

CREATE INDEX ix_tool_call_records_logical ON tool_call_records (logical_call_id);
```

**T8 才需要的结果句柄表：**

```sql
CREATE TABLE task_tool_results (
  id uuid PRIMARY KEY,
  task_id integer NOT NULL REFERENCES analysis_tasks(id) ON DELETE CASCADE,
  company_id integer NOT NULL,
  execution_attempt_id integer,
  tool_name varchar(64) NOT NULL,
  content jsonb NOT NULL,
  content_tokens integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
ALTER TABLE task_tool_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_tool_results FORCE ROW LEVEL SECURITY;
```

**为什么存数据库，不放 Redis：** 崩溃恢复后还要读到，而且需要 RLS。默认 7 天过期，由定时任务清理。

---

## 5. 失败路径

| 场景 | 系统行为 | 用户看到 |
|---|---|---|
| 经营库持续不可用 | 第 5 次 INFRA 后熔断打开；后续任务第 9 步立即失败 | 明确提示数据暂不可用，几秒内返回 |
| 熔断冷却结束 | 一个任务作为探测；成功就关闭，失败继续打开 | 恢复后自动正常 |
| Redis 不可用（熔断存储） | 熔断放行（`tool_guard.py:90` 的现有策略），不影响权限 | 无感知，失去快速失败 |
| 审计写入失败 | 先回滚会话再重试一次；再失败则当 INFRA，不返回结果 | 任务失败，**不允许无审计地返回数据** |
| 预占后 Worker 崩溃 | 配额不退还；恢复后新执行继续计算 | 可能多扣一次配额，安全方向 |
| 任务中途被取消 | 第 3 步抛 TASK_STOP，已写的审计保留 | 任务取消 |
| 权限在任务中途被收回 | 第 4 步拒绝，停止 | 任务按拒绝结束 |
| 工具结果超限 | `sql_query` 截断行并标记 `rows_left_out`；不能静默丢 | 报告说明数据不完整 |

---

## 6. 模型自选工具的循环 v2（T8、T9）

主链默认不启用。启用时的循环：

```text
for 每轮:
  1 上下文引擎压缩循环消息（见 02_context_engine.md），超预算就结束
  2 模型返回工具调用
  3 对每个调用：
      未登记或不在 Agent 的 LoopPolicy 中 → caller_error 回复
      参数校验失败 → caller_error 回复
      control 工具 → 校验后结束循环
      capability → handler 经流水线调用 backed_by
  4 工具结果标记 untrusted，大结果换成句柄和摘要
  5 按 error_class 决定继续还是停止
```

| 新增能力 | 做法 |
|---|---|
| Agent 工具范围 | 每个 Agent 一份 `LoopPolicy(tools, max_rounds, max_calls, max_repairs, max_seconds)` |
| handler 抛异常 | 循环捕获，转成 INFRA 回复并记录；TASK_STOP 继续向上抛 |
| 并行调用 | 只允许都是 `side_effect="read"` 的调用；串行写审计 |
| 句柄 | `{"result_id":"…","row_count":5000,"summary":…}`，用 `read_result(result_id, offset, limit)` 分页读取；校验同一任务 |

**灰度步骤：** `off` → `shadow`（实际结果仍用固定路线，只比较）→ `allowlist` → `all`。每一步都要比较准确率、费用和耗时。之前记录显示费用约 1.7 倍、准确率未提高，所以**没有胜出就保持关闭**。

---

## 7. 配置

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `TOOL_PIPELINE_MODE` | `legacy` | `legacy` / `enforce`，迁移完成后删除 |
| `TOOL_DEFAULT_MAX_RESULT_TOKENS` | 2000 | 定义可覆盖 |
| `TOOL_BREAKER_ENABLED` | `true` | 紧急开关 |
| `TOOL_RESULT_RETENTION_DAYS` | 7 | 结果句柄保留期 |
| `MODEL_TOOL_MODE` | `off` | 已有，增加 `shadow` |

单个工具的超时、重试和熔断值放在 `catalog.py`，进代码评审和版本。任务创建时把 `catalog_hash` 写进快照。

---

## 8. 落地步骤

每个工单一个提交。**验证命令是计划，尚未运行；** 测试命令都在 `backend/` 下执行。

### T1 注册表（行为不变）
- **新增：** `runtime/tools/definition.py`、`registry.py`、`catalog.py`；`tests/unit/runtime/test_tool_registry.py`。
- **修改：** `tool_runtime.py` 的 `TOOL_ALLOWED_ROLES`、`_tool_contract_version`、`_validate_input` 改读注册表。
- **验证：** `python -m pytest tests/unit/runtime -x -q`；再跑冒烟。
- **回滚：** `git revert`，无数据变化。

### T2 错误分类
- **新增：** `tools/errors.py`，全部错误码对照表；`test_tool_errors.py`（扫描代码里的错误码，要求都已登记）。
- **修改：** `ToolOutput` 增加 `error_class`；`knowledge/tool.py` 补 RAG 错误码；`tool_guard.py` 改用分类。
- **验证：** `python -m pytest tests/unit/runtime tests/unit/knowledge -x -q`。

### T3 流水线替换
- **新增：** `tools/pipeline.py`、`audit.py`；`test_tool_pipeline.py`（覆盖 13 步顺序和每步失败）。
- **修改：** `ToolRuntime.execute` 在 `enforce` 模式下调用流水线。
- **迁移：** 先让现有 `test_tool_runtime.py` 在两种模式下都通过，再切默认值。
- **验证：** 单元测试 → `tests/integration/workflow` → 冒烟。
- **回滚：** `TOOL_PIPELINE_MODE=legacy`。

### T4 每次执行写审计（**需批准：改表**）
- **新增：** Alembic 迁移（第 4 节）。
- **修改：** 流水线第 10、13 步，把重试移到 `ToolRuntime` 内部，**去掉内层 `GuardedTool` 的重试**。
- **验证：** 注入一次 INFRA 失败，断言 2 条记录、配额只扣 1 次。
- **回滚：** 新字段可空，代码回退不影响旧数据。

### T5 超时和结果大小
- **修改：** `pipeline.py` 增加耗时检查和 `on_overflow`；MCP 补子进程超时。
- **验证：** 构造慢工具和 5000 行结果。

### T6 主链接入熔断（**需批准：改主链行为**）
- **修改：** 所有工具统一走流水线熔断阶段，`nodes.py:472`、`:591` 不再区分路径。
- **验证：** 演练脚本停 `agent-demo_business_acme-1`，确认同公司任务 5 秒内失败、另一家公司不受影响，恢复后放行。

### T7 细粒度权限
- **修改：** `allowed_roles` 改为权限名（如 `data:query`）和“角色 → 权限”表。这是权限逻辑，**需批准**。
- **验证：** 权限矩阵测试：每个角色 × 每个工具。

### T8 循环 v2
- **修改：** `tool_loop.py` 接上下文引擎和 `LoopPolicy`；`results.py` 和结果句柄表（**改表**）。
- **验证：** 6 轮大结果不超预算；句柄不能跨任务读取。

### T9 灰度（**需批准，且会产生费用**）
- 按第 6 节执行，运行前先报次数和费用级别。

---

## 9. 怎么确认它真的生效

```bash
python -m pytest tests/unit/runtime -x -q
```

**上线后用任务号查（目标形态）：** 查 `tool_call_records` 时，能看到每次执行的版本、分类和 `catalog_hash`；`render_task_trace.py` 按 `logical_call_id` 把重试归到一组显示。

| 检查 | 通过标准 |
|---|---|
| 新增假工具只改 `catalog.py` | 其余代码零改动，测试通过 |
| 所有错误码已登记 | 扫描测试为 0 个未登记 |
| 模型传 `company_id=其他公司` | `scope_binder` 拒绝，0 次执行 |
| 模型传 `_runtime_timeout_ms` | 被 `extra="forbid"` 或覆盖，不生效 |
| 经营库故障 | 熔断生效；恢复后自动放行 |
| 冒烟和 SQL 评测 | 不低于切换前基线 |

**仍需开工时确认：** MCP 路径的错误码（第 3.3 节只列了部分）；工作流拒绝结束时报告的终态；`template_query` 的范围绑定（见总计划 B3，它现在用默认业务库凭据）。
