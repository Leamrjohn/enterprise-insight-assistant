# R3 之前的运行逻辑：讲解指南

这份文档写给**负责讲解的 AI**，学习者是本项目的用户。目标是让用户完全熟悉 R3 开工前的代码：每个函数做什么，代码和架构怎么搭起来，为什么要这样设计。

- 代码版本：提交 `e60bb4e`（2026-11-24，R2 段验收通过并合并 C10，R3 的 B1a 拆分之前）。
- 文中所有 `文件:行号` 都以这个提交为准，路径相对 `backend/app/`（另有说明的除外）。
- 全部 1418 个函数和类的清单见附录 [pre_r3_function_index.md](pre_r3_function_index.md)。

---

## 0. 给讲解 AI 的规则（先读完再开讲）

### 0.1 怎么读这个版本的代码

当前 `main` 已经有 R3 的改动，比如 `nodes.py` 已拆成 `nodes/` 包，所以行号会对不上。一律读 `e60bb4e`：

```bash
git show e60bb4e:backend/app/modules/workflow/orchestration/nodes.py
```

不要为了读代码新建 git worktree 文件夹，也不要改任何代码。

### 0.2 学习者情况

- 编程初学者，英语弱。全程用中文讲。英文术语第一次出现时，用一句白话解释，例如“lease（租约）：一段时间内只有我能处理这个任务的凭证”。
- 讲代码时列“文件:起止行”阅读清单，让用户自己打开看。不要贴带省略号的代码片段。
- 动手讲某个函数前，先给它在整条数据链路里的位置：谁调用它、传进来什么（真实字段名和示例值）、它返回什么、交给谁。
- 每讲一处，都把“模型判断的”和“代码强制的”分开讲。用户以前常把两者混在一起。
- 示例数据如果是编的，要标明“示意”。

### 0.3 每个函数讲到什么程度

逐个讲清：

1. 做什么、为什么需要它（没有它会出什么问题）。
2. 参数：名字、类型、一个真实例子。
3. 返回或写出什么：返回值、写了哪张表的哪些字段、发了什么事件。
4. 被谁调用、它又调用谁。
5. 失败时怎么样：抛异常、返回失败对象，还是降级。
6. 设计取舍：这样做的代价，还有没有别的做法。

### 0.4 怎么确认用户真懂了（每课结束必须做）

1. **复述**：让用户用自己的话讲一遍这一课的流程，从输入到输出。
2. **逐点考，不抽样**，由浅到深：
   - 定位：你给行号，用户说这几行做什么。
   - 为什么：为什么这样写，不这样写会怎样。
   - 预测：给一个新输入或故障场景，让用户预测系统怎么走、最后输出什么。**必须包含失败路径。**
   - 取舍：代价，以及其他做法。
3. 通过标准：每个要点都能做到“预测后果”这一级。答错了，先讲清错在哪，再换一道同类新题，不让用户重答原题。
4. 能运行的就运行：让用户先预测，再跑测试或命令，用真实输出对照。

### 0.5 用户的已知薄弱点（2026-11-18 评估，讲到相关处要重点抽查）

- 以为 Reviewer 会重跑前面的节点。实际上 Reviewer 只出评审结果，重跑由 `smart_router_node` 按代码规则决定。
- 以为“恢复投递走 Outbox”。实际上崩溃恢复由 beat 定时任务直接投递 Celery，Outbox 只负责新任务的首次投递。
- Data 节点的校验顺序记反。实际顺序：模型生成 SQL → 查询契约检查 → 模型语义复核 → 指标契约评估 → SQL Tool 里做 AST 和表范围校验 → 只读执行 → 结果评估。
- 把 RLS 写进 SQL 工具。实际上 RLS（行级安全：数据库按当前公司过滤行）只在**平台库**；经营库靠独立数据源连接、表白名单、只读事务来隔离。
- 以为只出现在记忆里的数字能通过数字校验，以为 Data 和 Knowledge 也读记忆。实际上记忆只给 Planner 和 Reviewer 读，不是证据。
- 把 `no_progress`（重复错误）说成模型决定的。实际上是代码比对指纹。
- 进程心跳（watchdog 文件）和执行租约（数据库里的 lease）容易混。

---

## 1. 系统全貌

### 1.1 一句话

用户在会话里提一个经营问题 → API 冻结这次提问能用的范围，写入任务和 Outbox → Worker 认领任务，跑一张 LangGraph 图（Planner → Data / Knowledge → Reviewer → 路由）→ 确定性校验 → 决定发布、部分发布、待人工审核或失败 → 前端轮询拿到结果。

### 1.2 进程和存储（见仓库根目录 `docker-compose.yml`）

| 服务 | 做什么 |
|---|---|
| `frontend` | Vue 前端，开发模式运行 |
| `api` | FastAPI：登录、会话、建任务、查结果 |
| `worker` | Celery Worker（后台任务进程），跑分析任务、文档入库、摘要等，并发 1，由 `app.core.watchdog` 包着 |
| `report-worker` | 另一个 Celery Worker，只监听 `reports` 队列。`backend/app` 里没找到发往这个队列的任务，讲解时请核实它的用途 |
| `beat` | Celery Beat（定时器），定时触发 Outbox 投递、租约恢复、搁浅任务对账、记忆清理 |
| `postgres` | 平台库（用户、公司、任务、审计、文档向量），带 RLS；经营库是另外配置的只读数据源 |
| `redis` | Celery 的消息队列和结果存储；工具断路器的计数也放这里 |
| `migrate` | 启动时跑 alembic 迁移 |
| `capacity-signal` | 磁盘容量信号服务，建任务前检查（`modules/workflow/lifecycle/capacity.py`） |
| `clamd`、`localstack` | 病毒扫描、S3 模拟，给附件上传用（上传入口目前冻结） |
| `otel-collector`、`tempo`、`prometheus`、`grafana`、`metrics-exporter` | 链路追踪、指标、看板 |

### 1.3 后端目录地图（`backend/app/`）

| 目录 | 职责 | 主链会不会经过 |
|---|---|---|
| `api/router.py` | 汇总所有路由 | 会 |
| `core/` | 配置、网关、日志、追踪、安全、Celery、中间件 | 会 |
| `core/config/` | K1 配置分域和配置快照 | 会 |
| `core/gateway/` | 模型网关（DeepSeek、OpenAI 兼容） | 会 |
| `modules/identity/` | 登录、令牌、当前用户 | 会 |
| `modules/organizations/` | 公司、成员、角色、经营数据源、契约快照 | 会 |
| `modules/conversations/` | 会话、消息、建任务、会话状态（M7）、滚动摘要（C9） | 会 |
| `modules/workflow/` | 任务模型、Outbox、Worker 任务、执行租约、检查点、LangGraph 图和节点、路由 | 会，核心 |
| `modules/analysis/planner/` | Planner 规划 | 会 |
| `modules/analysis/data/` | SQL 生成、校验、执行 | 会 |
| `modules/analysis/catalog/`、`metrics/` | 契约快照目录、指标评估、已确认事实 | 会 |
| `modules/knowledge/` | 文档检索 RAG、Knowledge Agent、MCP 适配 | 会 |
| `modules/reporting/` | Reviewer、报告组装、确定性校验、语义复核 | 会 |
| `modules/runtime/` | 模型预算、工具关卡、工具循环、断路器、上下文引擎、提示词注册 | 会 |
| `modules/memory/` | 跨任务记忆 | 会（只给 Planner 和 Reviewer） |
| `modules/reviews/` | 因果结论的人工审核 | 部分任务会 |
| `modules/documents/` | 文档上传、切块、向量化 | 不在一次提问里，但决定能检索到什么 |
| `modules/input_artifacts/` | 附件上传和处理（入口冻结） | 只在有已冻结附件时 |
| `modules/observability/`、`evaluation/` | 指标、评测 | 旁路 |

---

## 2. 一次提问的完整旅程

示意例子（编的）：分析员问“华东区 2026 年 9 月营收是多少？”，路线是 `data_only`。

每一步都写：谁做（代码还是模型）、在哪、出错怎么办。

### 第 1 步：登录（代码）

- `modules/identity/api.py:61-68` `login`：按用户名查用户，`verify_password` 校验密码，账户没启用返回 403，成功后 `create_access_token`（`modules/identity/authentication.py:12`）签发访问令牌。
- 之后每个请求由 `get_current_user`（`authentication.py:74`）解析 Bearer 令牌。
- 出错：用户名或密码错返回 401，不重试。

### 第 2 步：确定当前公司和权限（代码）

- `modules/organizations/access.py:28` `get_current_company_context`：查成员关系，必须是 `approved`；然后调用 `set_tenant_scope(db, company.id)`，把当前公司写进数据库会话变量，平台库的 RLS 从此只放行这家公司的行。
- `access.py:66` `require_analysis_permission`：只有 `owner`、`admin`、`analyst` 能提分析问题。
- 中间件 `core/middleware.py:62` `request_context_middleware`：生成请求 id；`_check_rate_limit`（`middleware.py:31`）只对带 `X-API-Key` 的请求限流（默认 60 秒 100 次，`core/config/security.py:17-18`）。
- 出错：403，不重试。

### 第 3 步：提交消息，冻结范围，建任务（代码，同一个数据库事务）

入口 `modules/conversations/api.py:306-351` `create_conversation_message_endpoint` → `modules/conversations/service.py:167-305` `create_conversation_task_service`：

1. **冻结文档范围**（185-199）：用户能看的已完成文档；前端传了文档 id 就必须是它的子集，否则 422。
2. **附件范围**（201-205）：只收已就绪、属于本人的附件版本。
3. 写入用户消息（208-214）。
4. **会话上下文快照**（215-253）：最近 8 条消息（`MAX_CONTEXT_MESSAGES`，`service.py:164`），`build_conversation_context` 按 token 截断；更早消息里的长期约束 `find_standing_constraints`；会话状态开着时冻结状态（M7，`freeze_state`）；摘要开着时冻结摘要（C9，`planner_summary`）。
5. **数据源检查**（254-269）：会话必须绑定经营数据源和当前契约快照，否则 409。
6. `create_task`（`modules/workflow/repository.py:66` 起）：
   - `_admit_task`（`repository.py:27-63`）：先查磁盘容量信号，再用 PostgreSQL advisory lock（咨询锁：数据库层面的互斥锁）串行计数；全局进行中任务不超过 20、单公司不超过 5（`core/config/admission.py:14-15`），超了返回 429，容量不安全返回 503。
   - 冻结一大批快照到任务行：配置快照 `config_snapshot` 和哈希（K4）、工作流版本、模型策略（模型名、超时 30 秒、最大输出 1024 token、价格表）、模型预算 `model_budget_snapshot`（`lifecycle/model_budget.py:16-51`）、追踪上下文 `trace_context`（O1）。工具策略和工具预算用 `modules/workflow/models.py` 里 `AnalysisTask` 的默认值（工具白名单 `rag_search`、`sql_query`、`template_query`；工具总调用 12 次、单个工具 6 次；SQL 超时 10000 毫秒）。
   - 写入任务和文档、附件的关联行。
7. `create_analysis_task_event`（`modules/workflow/delivery/outbox.py:31`）：在**同一个事务**里写一条 Outbox 事件。
8. 写一条空的助手消息，状态 `queued`，然后提交事务（294）。
9. 回到 API（`api.py:342`）：事务提交后立刻尝试 `publish_analysis_task_event`，把任务投给 Celery。返回 202 和任务 id。

**为什么这样设计**：任务和 Outbox 事件同生同死。API 进程如果在投递前崩溃，事件还留在库里，beat 每 5 秒会补投。这就是 Outbox 模式：先可靠地记下“要投递”，再投递。

**为什么要冻结**：任务可能排队，也可能重试很多次。这期间用户权限、配置、文档都可能变。冻结保证每一次执行都用创建那一刻的范围和规则，配置后来放宽了，也影响不到已经接收的任务。

### 第 4 步：投递（代码）

- `modules/workflow/delivery/outbox.py:43-100` `publish_analysis_task_event`：认领事件（发布租约 30 秒）→ 调 Celery `.delay` → 标记 `broker_accepted`；失败退回 `pending`。
- `beat` 定时任务（`core/celery_app.py:37-77`）：
  - 每 5 秒 `publish_pending_analysis_task_events`：补投还在 pending 的事件。
  - 每 10 秒 `recover_expired_analysis_executions`：租约过期的执行退回 `retrying`，再直接 `.delay` 投递（不经过 Outbox）。
  - 每 60 秒 `reconcile_stranded_analysis_tasks`：处理“已退回 retrying 但没 Worker 接手”的任务。
- Celery 配置：`task_acks_late=True`（任务做完才确认，Worker 崩溃时消息会重新投递）、`worker_prefetch_multiplier=1`（一次只拿一个）。

### 第 5 步：Worker 认领任务（代码）

`modules/workflow/tasks.py:650-1004` `process_analysis_task`（Celery 任务，`max_retries=3`）：

1. `claim_execution`（`lifecycle/execution.py:279-451`）：只认领 `queued` 或 `retrying` 的任务，原子地建一条执行尝试 `TaskExecutionAttempt`，写入执行租约（120 秒，`core/config/model.py:12`）。重复投递时只有一个能认领成功，其他的直接返回。如果是重试，还会算出从哪个节点续跑（`resume_next_node`）和可以复用的状态（`resume_state`）。
2. 开追踪 span（672-685）、进入配置快照作用域 `task_config_scope`（688-690，K4：本次执行读的配置一律来自快照）。
3. `set_tenant_scope(db, record.company_id)`（699-700）。
4. 助手消息改为 `running`。
5. 检查是否已取消（709）。
6. 如果是人工审核通过后的“只发布”任务，走 `_publish_approved_draft`（712-715），不再跑图。
7. 准备输入：冻结的文档 id（717-722）、附件上下文（729-738）、**Planner 记忆** `select_planner_memories`（739-745，`modules/memory/service.py:78`），写一条 `context_selected` 事件（747-763），影子记录问题事实（764，B2c，只记录不生效）。
8. 建 `ToolRuntime`（772-780）：带着任务 id、公司 id、允许的文档 id。
9. 再次核对经营数据源和契约快照属于这家公司（781-800），不对就抛错。
10. 进入 `model_call_scope`（模型调用记账作用域）和 `_maintain_execution_lease`（续租线程，`tasks.py:396-432`），然后 `run_analysis` 跑图（812-832）。

**租约和心跳的区别**：租约是数据库里的 `lease_expires_at`，由续租线程用独立的数据库会话续期，证明“这个执行还活着、还归我”。watchdog 心跳是 Worker 进程写的文件，给容器健康检查用（O4）。前者管任务归属，后者管进程存活。

### 第 6 步：跑图（代码编排，模型参与其中几个节点）

图的结构在 `modules/workflow/orchestration/graph.py:108-192`：

```
START → (从检查点续跑？) → state_extract_node → planner_node → planner_semantic_review_node
  ├─ analyze + data_only/hybrid → data_node ─┬─ hybrid → knowledge_node → reviewer_node
  │                                          └─ data_only ─────────────→ reviewer_node
  ├─ analyze + knowledge_only → knowledge_node → reviewer_node
  ├─ 直接回答/超出范围/反问/拒绝 → planner_terminal_node → END
  └─ 计划无效或失败 → planning_failure_node → END
reviewer_node → smart_router_node ─┬─ 停止 → END
                                   └─ retry_data / retry_knowledge / retry_reviewer / replan → 对应节点
```

- `_route_from_start`（51-54）：检查点里记录的下一节点只要在白名单 `_RESUMABLE_NODES`（24-36）里就从那里续跑，否则从头开始。
- `_route_after_planner`（57-82）：只看计划的 `action` 和 `route` 字段。计划无效就去 `planning_failure_node`，绝不把坏计划交给 Agent。
- `MAX_GRAPH_STEPS = 20`（37）：LangGraph 的递归上限，防止图无限循环。
- `run_analysis`（199-293）：组装初始状态；续跑时只从检查点里取白名单字段（263-292），检查点不能覆盖用户、公司、文档这些范围字段。
- 每个节点都被 `_traced`（40-48）包一层追踪 span。

每个节点完成后调用 `_checkpoint`（`nodes.py:100-148`），把白名单字段存进检查点表（经由 `tasks.py:352-382` `_checkpoint_workflow_node` → `execution.py:547` `checkpoint_workflow_state`）。如果这时执行已经不归自己（租约被别人收回），就不写。

各节点详见第 3 节。

### 第 7 步：图跑完后（代码）

回到 `tasks.py:834-845`：

- 终止结果标记了 `retryable`，就抛 `RetryableAnalysisTaskError`，进入任务级重试（见第 4 节）。
- 再查一次是否已取消。
- `_save_workflow_result`（`tasks.py:480-598`）：
  1. `validate_report`（`modules/reporting/validation.py:14-38`）：报告必须符合 `FinalAnalysisReport` 结构，引用的文档块必须在任务冻结的范围内（`_frozen_allowed_chunk_ids`，`tasks.py:87-106`）。
  2. `_deterministic_validation_result`（109-127）：汇总 schema、数字、引用三项校验结果，加上报告是否通过结构校验。
  3. 抢先写阶段 `saving_result`，再查一次取消，影子记录计划规则（B2d，只记录）。
  4. `decide_completion`（`modules/workflow/lifecycle/publication.py:35-84`）决定任务状态，见第 6 节。
  5. 需要人工审核的，把报告挪到 `report_draft`，建审核请求。
  6. `finish_execution`（`execution.py:591-682`）：只有执行仍归自己时才写终态。
  7. 报告是 completed 或 partial 时写入记忆 `persist_report_memory`；保存会话状态（版本号防并发覆盖，`_save_conversation_state` 435-458）；需要反问时记录缺失字段；同步助手消息；提交。
  8. 发布成功后排一个摘要任务 `_queue_summary`（461-477，C9，尽力而为）。

### 第 8 步：前端拿结果（代码）

前端轮询会话任务接口（`conversations/api.py:213` `get_conversation_task_endpoint`）和消息列表，看到助手消息状态变成终态，就展示报告。

---

## 3. 九个节点逐个讲

文件 `modules/workflow/orchestration/nodes.py`。每个节点都是“读 state → 调 Agent 或服务 → 写 state → 存检查点”。

### 3.1 `state_extract_node`（177-213）——M7 会话状态

- 只有 API 冻结了会话状态（模式是 shadow 或 enforce）才运行，否则直接返回空。
- **模型**只提议状态更新（`conversations/state_extractor.py` 的 `extract_state_update`）；**代码** `apply_update` 只保留用户原话能支持的更新，其他的记为 rejected。
- 提取失败就保留冻结时的状态，规划不依赖它。
- 有自己单独的 1 次模型调用额度（`model_budget.py` 里的 `state_extract_max_calls`），不占回答路径的额度。
- 截至 e60bb4e 的部署记录：`CONVERSATION_STATE_MODE` 已切到 enforce（`docs/worklog.md` 2026-11-22 M7c 段）。代码默认值是 off（`core/config/context.py:36`）。

### 3.2 `planner_node`（247-333）——规划

- **模型**判断问题类型，输出结构化计划：`action`（analyze、direct_response、scope_exit、needs_clarification、refuse），analyze 时还有 `route`（data_only、knowledge_only、hybrid）和 `intent`（需要哪些业务能力），以及改写后的独立问题 `resolved_question`。
- 输入：问题、会话上下文（`_planner_conversation_context` 219-236：enforce 模式下用提取出的状态替换正则找到的长期约束）、摘要（`_planner_history_summary` 239-244，只在摘要 enforce 时）、Planner 记忆、附件、路由反馈、重试上下文。
- 内部：`PlannerAgent.run`（`analysis/planner/planner_agent.py:37-98`）→ `PlanningService.decide`（`analysis/planner/planning.py:388-559`）。模型输出不过 `PlannerDecision`（`planner_decision.py:77-182`）的 JSON 校验时，用修复提示词再问，最多 `planner_max_attempts = 2` 次（`core/config/model.py:30`）。上下文超预算时 `context_too_long_decision`（`planning.py:218-230`）直接反问，不调模型、不扣费。
- 成功：写 `plan` 和 `scope_fingerprint`（范围指纹，`router.py:37-51`：用户、公司、文档、问题、路线、数据源、契约快照的哈希）。
- 失败：写 `planner_failure`，下一步去 `planning_failure_node`。

### 3.3 `planner_semantic_review_node`（336-475）——计划语义复核

- **模型**再看一遍计划是否和契约快照对得上（`reporting/semantic_review_service.py` 的 `SemanticReviewService.review_plan`）。
- **代码** `enforce_explicit_document_evidence_contract`（`planner_decision.py:42-74`）保证只问文档的问题不会被扩成数据查询。
- 复核失败：可重试的错误清空计划、走 `planning_failure_node`，让任务级重试从这个节点续跑；不可重试的错误改成反问，走 `planner_terminal_node`。
- 计划是 analyze 但没写 `intent`：改成反问（418-453）。
- 这不是安全防线。安全靠后面的 SQL 校验和工具关卡。

### 3.4 `planner_terminal_node`（478-503）和 `planning_failure_node`（506-522）

- 终止节点：反问时用 `_render_clarification`（75-91）生成问题，过滤掉表名列名这类内部名字（`_INTERNAL_NAME`，69）；其他动作用计划里的 `response_message`。
- 失败节点：统一回答“本次分析暂未完成，请稍后重试”，带上 `retryable` 标记，交给 Worker 判断要不要任务级重试。

### 3.5 `data_node`（657-860）——经营数据

选择 Agent（666-703）：

- 默认（`model_tool_mode=off`，`core/config/tool.py:14`）：`DataAgent`，SQL 工具被 `ToolRuntime.wrap` 包住。模型不调工具，只生成 SQL。
- 公司在白名单或模式是 all 时：`ToolCallingDataAgent`（`analysis/data/tool_agent.py`），模型在工具循环里自己调 `sql_query`。工具先套 `GuardedTool` 和断路器，再套 `ToolRuntime`。

`DataAgent.run`（`analysis/data/data_agent.py:100-396`）的顺序，这是用户容易记反的地方：

1. 路由反馈要求“重放已校验 SQL”时，直接 `_replay_validated_sql`（458-523），不调模型。
2. **模型**生成候选 SQL 和查询契约（`sql_generation.py` 的 `SQLGenerationService.generate`）。可重试的模型错误或 JSON 不合格时重新生成，总共最多 `data_max_attempts = 2` 次（`core/config/model.py:31`）。
3. **代码**检查查询契约：没有契约返回 `query_contract_missing`；没覆盖计划要求的能力返回 `query_contract_incomplete`；多出计划没要求的能力返回 `query_contract_out_of_scope`（182-229）。
4. **模型**做 SQL 语义复核 `review_sql`（233-259）：结论是 `insufficient_schema` 就停；结论是 `repair` 就带着原因重新生成，次数用完返回 `sql_semantic_unsupported`。
5. **代码**做指标契约评估 `assess_metric_query`（294-322）。
6. **代码**执行：`SQLTool.execute`（`analysis/data/sql_tool.py:39-129`）→ `execute_readonly_sql`（`sql_executor.py:99-161`）：
   - `validate_sql`（`sql_validator.py:10-24`）：用 sqlglot 解析出 AST（抽象语法树：把 SQL 拆成结构化的树），只允许单条 SELECT、没有副作用函数、每张物理表都在契约快照里。
   - 自动补 `LIMIT 1000`（`_apply_row_limit` 22-36）。
   - 用这家公司自己的数据源连接，`default_transaction_read_only=on`，再 `SET TRANSACTION READ ONLY`，设置 `statement_timeout`。
   - 敏感字段脱敏（`_mask_sensitive_rows` 39-54）。
   - 各种数据库错误映射成错误码，并标明能不能修（`sql_tool.py:76-129`）：校验不过、超时、分组错误可修，会把原因带回给模型重新生成；权限不足、其他执行错误不可修。
7. **代码**评估结果 `assess_query_result`（`query_validation.py:11-60`）：数据库执行成功不等于回答了问题，结果形状不对或查不到记录都算证据不足。

`data_node` 再把结果映射成 `NodeOutcome`（节点结果契约，`orchestration/node_outcome.py`）：

| Agent 结果 | data_result.status | NodeOutcome.status | 路由会怎么做 |
|---|---|---|---|
| 成功 | ready | succeeded | 继续 |
| `no_matching_records` | insufficient_evidence | no_matching_records | 停止，这是事实，不是错误 |
| `sql_semantic_unsupported`、`query_contract_incomplete` | insufficient_evidence | repairable_error | 重新规划 |
| `insufficient_schema` 等 | insufficient_evidence | insufficient_evidence | 视另一边证据而定 |
| 数据库失败、生成失败、次数用完 | failed | retryable_error | 重试 Data |
| 其他失败 | failed | denied | 停止 |

成功时还会用 `build_confirmed_facts` 生成“已确认事实”，后面给 Knowledge 和 Reviewer 用。

### 3.6 `knowledge_node`（554-654）——文档证据

- 默认用 `KnowledgeAgent`（`modules/knowledge/agent.py:133-238`）；工具模式开启时用 `ToolCallingKnowledgeAgent`。
- 检索工具 `RAGTool.execute`（`knowledge/tool.py:63-286`）：向量检索加关键词检索，RRF 融合（RRF：把几路排序合并成一个排序的算法），再重排。默认参数在 `core/config/rag.py:14-22`：召回 10 条、最低分 0.1、重排保留 3 条、重排最低分 0.5。
- `KNOWLEDGE_EVIDENCE_TRANSPORT=mcp_stdio` 时改用 MCP 子进程读证据（`knowledge/mcp_adapter.py`）；工具模式下 MCP 失败会切回本地（`_guarded_rag_tool` 536-551 里的 `FallbackTool`）。
- **模型**根据检索到的文档块写回答并标注引用；`support_check` 开着时（默认开，`core/config/flags.py:11`），`_cited_output`（`agent.py:240-318`）只保留有依据的部分。
- 成功但没证据：`insufficient_evidence`。检索失败：`knowledge_retrieval_failed` 可重试，其他错误码一律 denied。

### 3.7 `reviewer_node`（887-979）——组装报告和评审

`ReviewerAgent.run`（`reporting/reviewer_agent.py:271-723`）：

1. **代码** `compose_report`（`reporting/composer.py:36`）把数据证据和文档证据组装成结构化报告。
2. **模型**做证据语义复核 `review_evidence`（`reviewer_agent.py:295` 起）：检查结论是否被证据支持、文档限定条件、哪些记忆和证据矛盾。复核没完成也不影响发布判断，发布仍然只看确定性校验。
3. **代码**确定性校验 `_validate_final_answer`（76-127）：
   - `validate_schema`：回答结构对不对，有文档证据时必须有引用。
   - `validate_numbers`：回答里的每个数字都必须能在数据结果或文档证据里找到。
   - `citations_valid`：引用的文档块必须属于本用户、在本次检索结果里（数据库校验器 `validate_citations` 在 `nodes.py:896-897` 挂上）。
   - `coverage`：关键词覆盖率只作诊断，不卡发布。
4. `_flag_contradicted_memories`（`nodes.py:863-884`）：模型认为和证据矛盾的记忆暂停使用。这一步失败不影响报告。
5. 节点把结果归成 `passed`、`partial`、`validation_failed`、`exhausted`（918-934）。

Reviewer 不会重跑任何节点。

### 3.8 `smart_router_node`（982-1079）——确定性路由

- `choose_next_action`（`router.py:70-168`）只读结构化状态，不问模型，也不看回答文字。优先级：
  1. 确定性校验失败（`_validation_action` 54-67）：引用校验失败直接停（安全问题）；数字或结构失败就重新规划。
  2. 按 Data、Knowledge、Reviewer 的顺序看 `NodeOutcome`：cancelled 停；denied 停；no_matching_records 停；repairable_error 时 Data 和 Reviewer 重新规划，Knowledge 重试检索；retryable_error 重试对应节点。
  3. 再看证据状态组合（119-166），比如 data_only 数据 ready 就停并判为完整，两边都不足就停并判为证据不足。
  4. 都不匹配：停，原因 `non_retryable_or_unknown_failure`。
- 图内重试次数用完（`external_retry_count >= 2`，`MAX_EXTERNAL_RETRIES`，`router.py:16`）就强制停。
- 不停时：`build_feedback`（171-230）给目标节点写反馈（比如重放上次 SQL，或保持范围重新检索）；`recovery_decision_for_node`（`lifecycle/recovery.py:100-102`）查白名单策略，清掉会失效的下游状态；写 `retry_context`；计数加 1。
- 每一轮都追加到 `loop_history`，最后存进结果，方便排查。

---

## 4. 失败和重试：四层

| 层 | 在哪 | 什么时候触发 | 次数上限 | 怎么重来 |
|---|---|---|---|---|
| 1. 节点内部 | Planner、Data、Knowledge 各自的 Agent | 模型输出不合格、可修的 SQL 错误 | Planner 2 次、Data 2 次（`core/config/model.py:30-31`）；工具循环：模型重试 1 次、修复 2 次（`core/config/tool.py:20-22`）；`GuardedTool` 对基础设施故障重试 1 次 | 同一节点内带着错误原因重新问模型 |
| 2. 图内路由 | `smart_router_node` | 节点给出可重试或可修的结果，或确定性校验失败 | 2 次（`router.py:16`）；整张图最多 20 步（`graph.py:37`） | 回到 Data、Knowledge、Reviewer 或 Planner |
| 3. 任务级 | `process_analysis_task` 的异常处理（`tasks.py:847-995`） | 终止结果带 `retryable`，或可重试的异常（数据库瞬时错误、连接错误、超时、可重试的模型错误，见 `_is_retryable_exception` 189-199） | 3 次（`@celery_app.task(max_retries=3)`，650） | 状态改成 `retrying`，等待 `2^(n+1) × (0.5～1.5)` 秒（`_retry_countdown` 202-206），新执行从失败节点续跑，复用之前可信的检查点 |
| 4. 进程崩溃 | beat 定时任务 | 租约过期（Worker 死了，没人续租） | 租约过期恢复本身没有看到次数上限，讲解时请核实；搁浅对账最多重投 10 次或 30 分钟（`outbox_tasks.py:22-25`），超过就判失败 | `recover_expired_executions`（`execution.py:771-838`）把任务改回 retrying，把还没结算的模型调用记为 unknown，然后直接投 Celery |

**不重试、直接收尾的情况：**

- 模型预算用完 `ModelBudgetExceeded`（`tasks.py:899-931`）：任务判 `partial`，`result_data` 换成预算耗尽说明。**已有的报告不会保留**，这是已知缺口。
- 不可重试的异常：判 `failed`（966-995）。
- 用户取消：每个不可逆操作之前都用 `_stop_if_cancelled`（282-307）重新查一次。

---

## 5. 限制和预算一览（代码默认值）

部署时可以用环境变量覆盖。只能看键名，不要打印 `.env` 的值。

| 限制 | 默认值 | 在哪定义 | 在哪执行 |
|---|---|---|---|
| 单任务模型调用（回答路径） | 8 次 | `core/config/model.py:24` | `model_governance.py:268-401` `reserve_model_call` |
| 单节点模型调用 | 4 次 | `model.py:25` | 同上 |
| 修复调用 | 2 次 | `model.py:26` | 同上 |
| 单任务 token | 16000 | `model.py:27` | 同上，调用前按“提示词估算 + 最大输出”预占 |
| 单任务费用 | 0.15 | `model.py:28` | 同上，未定价的调用记为 unknown |
| 状态提取、摘要的单独额度 | 各自 1 次，token 另加 | `lifecycle/model_budget.py:33-50` | 同上 |
| 模型超时、最大输出 | 30 秒、1024 token | `model.py:21-23` | 网关读冻结值 |
| 工具调用 | 总 12 次、单个 6 次 | `workflow/models.py` 的 `tool_budget_snapshot` 默认值；`runtime/schemas.py:57` | `tool_runtime.py:356-370` `_reserve_call` |
| 工具循环 | 6 轮、8 次工具、2 次修复、90 秒；Knowledge 4 轮、5 次 | `core/config/tool.py:18-25` | `runtime/tool_loop.py:150-240` |
| SQL | 超时 10000 毫秒、最多 1000 行 | 任务的 `tool_policy_snapshot`、`sql_executor.py:102-103` | `sql_executor.py` |
| 同时进行的任务 | 全局 20、单公司 5 | `core/config/admission.py:14-15` | `repository.py:27-63` |
| 会话历史 | 最近 8 条 | `conversations/service.py:164` | `build_conversation_context` |
| Planner 记忆 | 1024 token | `core/config/memory.py:11` | `memory/service.py` |
| 执行租约 | 120 秒 | `core/config/model.py:12` | `execution.py` |
| 图步数、图内重试、任务级重试 | 20、2、3 | 见第 4 节 | 见第 4 节 |

所有预算都在建任务时冻结进任务行，执行时从任务行读，客户端改不了。预算用量记在任务行上，所以任务级重试共用同一份预算。

---

## 6. 发布判定：`decide_completion`

`modules/workflow/lifecycle/publication.py:35-84`，纯代码，按顺序判断：

| 条件 | 任务状态 | 报告放在哪 |
|---|---|---|
| 终止结果是反问 | `needs_clarification` | 无 |
| 终止结果是 failed，或没有回答文字 | `failed` | 无 |
| 评审是 partial，或报告状态是 partial | `partial` | 有报告就放 `report` |
| 报告里有因果推断，需要人工审核（`reviews/service.py` 的 `requires_human_review`） | `awaiting_review` | `report_draft`，管理员审核通过后由 `_publish_approved_draft` 重新校验再发布 |
| 有报告 | `completed` | `report` |
| 没报告（直接回答） | `completed` | 无 |

冒烟测试里的混合题经常停在 `awaiting_review`，原因就是这一条。

---

## 7. 安全边界（全部由代码强制，模型不能改）

1. **身份和公司**：每个请求都从令牌解析用户，从成员关系确定公司，然后设置租户范围。
2. **平台库 RLS**：`set_tenant_scope`（`db/session.py`）设置会话变量，RLS 策略按公司过滤。Worker 在 `tasks.py:699-700` 也会设置。
3. **经营库隔离**：每家公司用自己的数据源连接（`sql_executor.py:172-189` `_connection_details`，不记录密码）；表白名单来自这家公司的契约快照；只读事务；超时；行数上限；敏感字段脱敏。经营库没有 RLS。
4. **SQL 校验**：AST 解析，只允许单条 SELECT，禁止有副作用的函数，所有物理表都必须在快照里（`sql_validator.py`）。不接受用户写的 SQL，只执行模型生成并通过校验的 SQL。
5. **工具关卡** `ToolRuntime._execute`（`runtime/tool_runtime.py:386-471`），按顺序：
   1. 工具在任务冻结的白名单里。
   2. 发起人**现在**仍然有权限（冻结范围和当前成员关系取交集，`_validate_current_authorization` 202-225）。
   3. 输入通过工具登记的参数结构校验（`_validate_input` 302-327）。
   4. 公司范围和文档范围对得上冻结值（`_validate_scope` 176-200）。
   5. 冻结的文档用户现在仍然看得见（`_validate_current_document_scope` 266-300）。
   6. 服务端参数（比如超时）由策略附加，模型不能指定（`_with_server_parameters` 329-348）。
   7. 扣工具预算（`_reserve_call` 356-370）。
   8. 执行，写 `tool_started` 和 `tool_completed`/`tool_failed` 事件、`ToolCallRecord`（只记元数据，不记内容）。
6. **断路器**（`runtime/tool_guard.py`）：只统计基础设施故障。模型写错 SQL 不算，否则一条坏 SQL 就能把数据库工具关掉。断路器状态放在 Redis，Redis 坏了就放行，因为它保护的是工具，不是安全控制。
7. **引用范围**：报告引用的文档块必须在任务冻结的文档范围内（`validate_report`），回答里的引用必须属于本用户且在本次检索结果里。
8. **上传入口冻结**：附件和文件上传入口保持冻结，不开放。

---

## 8. 横切机制（R1、R2 加进来的，用户大多没参与实现）

讲这些时，先讲“没有它之前会出什么问题”，再讲它怎么接进主链。

| 工单 | 机制 | 主要文件 | 接入点 |
|---|---|---|---|
| K1、K2 | 配置分域、配置目录和严格模式 | `core/config/` 下各个域文件、`catalog.py` | `get_settings()` |
| K4 | 建任务时冻结配置快照，执行时只读快照 | `core/config/snapshot.py` | `repository.py` 的 `create_task`、`tasks.py:688-690` 的 `task_config_scope`、节点里的 `runtime_settings()` |
| G1 | 提示词注册表，带版本号 | `modules/runtime/prompts.py` | `tasks.py:807` 的 `prompt_version`；各 Agent 取提示词 |
| C1 | 分词器，准确数 token | `core/tokenizer.py` | 预算预占、上下文引擎 |
| C2 | 每次模型调用按段记录 token | `modules/runtime/context_measurement.py` | `reserve_model_call` 里的 `resource_usage` |
| C3 | 上下文清单：策略版本、每段 token、处理方式、哈希 | `modules/runtime/context/manifest.py` | `model_context_scope`，和预占在同一个事务里写入 |
| C4、C5 | 上下文引擎：每次模型调用能看到什么，超预算直接拒绝，不扣费 | `modules/runtime/context/engine.py`、`policies/` | Planner、SQL 生成、语义复核、Knowledge 回答；抛 `ContextBudgetExceeded` |
| C6、M7 | 会话状态：模型提议，代码按用户原话核对 | `conversations/state*.py` | API 冻结 → `state_extract_node` → Planner → 发布时保存 |
| C7 | 证据摘录 | `knowledge/`、`reporting/` | Knowledge 回答、报告 |
| C8 | Knowledge 上下文门槛 | `knowledge/agent.py` 的 `answer_context_manifest`（42-69） | Knowledge 回答前 |
| C9 | 异步滚动摘要：发布后另起任务写摘要，下次建任务时冻结 | `conversations/summary*.py`、`workflow/summary_tasks.py` | `_queue_summary` → `summarize_conversation`；API 冻结摘要；Planner 在 enforce 下读。部署记录：2026-11-24 已开 enforce |
| C10 | Planner 系统提示词精简 | `analysis/planner/planning.py` | 提示词 |
| O1 | 链路追踪：API 和 Worker 串成一条 trace | `core/tracing.py` | 建任务存 `trace_context`，Worker 继续这条 trace；每个节点、工具一个 span |
| O2、O3 | 看板、告警 | `ops/`、`modules/observability/` | 旁路 |
| O4 | Worker 进程心跳和看门狗 | `core/watchdog.py`、`core/heartbeat.py` | compose 的启动命令 |
| E 系列 | CI、锁文件、导入规则、测试分层、安全扫描、行为门禁 | `.github/`、`backend/requirements/`、`backend/tests/` | 不影响运行，只影响开发流程 |

---

## 9. 已知缺口和待核实的疑点

讲到对应位置时提出来，让用户判断风险。下面标“待核实”的，是以前排查时发现的疑点，讲解 AI 要先读代码确认，不要直接当结论。

1. 模型预算耗尽时，已经生成的报告被丢弃，任务只留预算耗尽说明（`tasks.py:899-931`）。
2. 待核实：租约过期恢复是否有次数上限（`execution.py:771-838`、`claim_execution`）。
3. 没有看到整个任务的总超时，只有各层的次数上限和单次调用超时。
4. 限流只对带 `X-API-Key` 的请求生效（`middleware.py:31-61`），用 Bearer 令牌登录的用户不受这个限流。
5. 待核实：data_only 路线确定性校验失败后，报告是否会降级（看 `reviewer_agent.py` 里调用 `_validate_final_answer` 之后的几个返回分支）。
6. 影子功能只记录不生效：问题事实（B2c，`tasks.py:237-255`）、计划规则（B2d，`tasks.py:258-279`）、Planner 规则 R4。

---

## 10. 推荐的讲课顺序

每课先给阅读清单，再讲，最后按 0.4 节考察。前一课没通过不进下一课。

| 课 | 主题 | 阅读清单（e60bb4e） | 必考要点 |
|---|---|---|---|
| 1 | 系统全貌 | `docker-compose.yml`（服务列表）、`core/celery_app.py:24-77`、`api/router.py` | 每个服务做什么；平台库和经营库的区别 |
| 2 | 登录和公司上下文 | `identity/api.py:61-68`、`identity/authentication.py:12-79`、`organizations/access.py:28-72`、`db/session.py`、`core/middleware.py` | RLS 在哪生效、在哪不生效；限流只管哪类请求 |
| 3 | 提问入口和冻结 | `conversations/api.py:306-351`、`conversations/service.py:164-305`、`workflow/repository.py:27-139`、`lifecycle/model_budget.py`、`core/config/snapshot.py` | 冻结了哪些东西，为什么要冻结；准入失败返回什么状态码 |
| 4 | Outbox 和投递 | `workflow/delivery/outbox.py`、`workflow/outbox_tasks.py`、`core/celery_app.py:56-77` | API 在投递前崩溃会怎样；恢复投递走不走 Outbox |
| 5 | Worker 认领、租约、检查点 | `workflow/tasks.py:385-432, 650-845`、`lifecycle/execution.py:43-588`、`lifecycle/checkpoint.py`、`lifecycle/execution_attempt.py` | 两个 Worker 同时拿到同一任务会怎样；租约和进程心跳的区别 |
| 6 | 图和状态 | `orchestration/graph.py`、`orchestration/state.py`、`orchestration/node_outcome.py`、`nodes.py:94-165` | 坏计划会不会进 Data；续跑能不能改公司范围 |
| 7 | 会话状态和摘要 | `nodes.py:168-244`、`conversations/state.py`、`state_extractor.py`、`state_update.py`、`summary.py`、`summarizer.py`、`workflow/summary_tasks.py` | 模型提议和代码核对的分工；摘要失败会不会影响回答 |
| 8 | Planner 和语义复核 | `nodes.py:247-522`、`analysis/planner/` 全部、`reporting/semantic_review_service.py`、`runtime/prompts.py`、`runtime/context/engine.py` | 计划 JSON 不合格会怎样；语义复核失败分两种情况各去哪 |
| 9 | Data 节点 | `nodes.py:657-860`、`analysis/data/data_agent.py`、`sql_generation.py`、`query_contract.py`、`sql_tool.py`、`sql_validator.py`、`sql_executor.py`、`query_validation.py`、`analysis/metrics/` | 七步顺序；每种 SQL 错误能不能修；查不到记录为什么直接停 |
| 10 | 工具关卡和工具循环 | `runtime/tool_runtime.py`、`tool_guard.py`、`tool_loop.py`、`analysis/data/tool_agent.py`、`knowledge/tool_agent.py`、`nodes.py:525-551` | 工具关卡八步；坏 SQL 会不会打开断路器；默认模式下模型调不调工具 |
| 11 | Knowledge 和 RAG | `nodes.py:554-654`、`knowledge/agent.py`、`knowledge/tool.py`、`knowledge/rag/`、`knowledge/mcp_adapter.py`、`documents/`（入库部分） | 检索、融合、重排、支持度检查各由谁做；MCP 失败怎么办 |
| 12 | Reviewer 和确定性校验 | `nodes.py:863-979`、`reporting/reviewer_agent.py`、`composer.py`、`numeric_validation.py`、`citation_validation.py`、`schema_validation.py`、`validation.py` | 报告是谁组装的；三项校验各查什么；记忆为什么不是证据 |
| 13 | 路由和恢复策略 | `nodes.py:982-1079`、`orchestration/router.py`、`lifecycle/recovery.py` | 给五种状态组合，预测路由动作；引用失败为什么直接停 |
| 14 | 保存和发布 | `tasks.py:87-127, 435-640`、`lifecycle/publication.py`、`reviews/`、`memory/service.py` | `decide_completion` 六种结果；人工审核通过后还校验什么 |
| 15 | 模型网关和预算 | `core/gateway/`、`runtime/model_governance.py`、`core/tokenizer.py`、`runtime/context_measurement.py`、`runtime/context/manifest.py` | 预占和结算；租约过期时没结算的调用怎么处理；预算用完任务变成什么状态 |
| 16 | 失败全景复习 | 第 4、5 节涉及的所有位置 | 给一个故障场景（比如经营库连不上、DeepSeek 超时、Worker 被杀），让用户从头说到尾 |
| 17 | 观测 | `core/tracing.py`、`core/watchdog.py`、`core/heartbeat.py`、`modules/observability/`、`workflow/audit/` | 一个任务能在哪几处查到记录；事件、模型调用、工具调用各记了什么 |

不在主链上、可以最后讲或跳过的部分：`modules/input_artifacts/`（附件处理，上传入口冻结）、`modules/organizations/` 的管理接口、`modules/evaluation/` 和 `backend/scripts/evaluation/`（评测和冒烟）。

---

## 11. 附录

- 全部函数和类的清单：[pre_r3_function_index.md](pre_r3_function_index.md)。由脚本从 e60bb4e 自动生成，每行包含名字、起止行、参数和返回类型、docstring 第一行。约一半的函数没有 docstring，那一列为空，讲解时要读代码。
- 讲到每个文件时，用清单核对有没有漏讲的函数。
