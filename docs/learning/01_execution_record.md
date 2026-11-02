# 01 执行记录（Claude 的完整行为记录）

按时间顺序记录每个工单：做了什么、执行了哪些命令、得到什么真实结果、没覆盖什么。
“为什么这么做、还有什么别的办法”见 [02_design_decisions.md](02_design_decisions.md)；概念讲解与练习见 [03_teaching_guide.md](03_teaching_guide.md)。

约定：所有数字都来自当次运行的真实输出；未运行的内容明确写“未验证”。

---

## 0. 接手分析（2026-11-01，只读）

| 步骤 | 做了什么 | 结果 |
|---|---|---|
| 0.1 | 读 `git log`、`docs/STATUS.md`、`docs/worklog.md`、README、compose 服务名 | 132 个提交；阶段 1 三轮基线 21/24 成功（87.5%），阶段 2 做到 2.4 |
| 0.2 | 按代码追踪主链：`conversations/api.py` → `workflow/tasks.py:process_analysis_task` → `orchestration/graph.py` → `_save_workflow_result` | 画出端到端流程图与 LangGraph 节点图；发现旧 `workflow/api.py` 的 `/tasks` 未被挂载（只搜索了引用，未运行验证） |
| 0.3 | 逐模块读记忆、上下文、工具、兜底、RAG、SQL、提示词实现 | 结论：治理与兜底接近生产级；记忆检索、上下文压缩、RAG 召回、模型选工具、提示词评测较初级 |

## 1. 计划补充 04（提交 8490742）

- 读 `docs/roadmap/00～03`，对照源码判断：可靠性、SQL、治理覆盖充分；缺组件评测台、模型选工具、提示词工程、跨模块联动；RAG 与记忆被列为“可砍”与学习目标冲突。
- 新增 `docs/roadmap/04_agent_capability_track.md`（阶段 2.5、4.5、7.5，7.2/7.3 细则，跨模块联动矩阵）；修改 00 的分工、阶段表、保留顺序。
- 只改文档。

## 2. 工单 2.3：日志关联编号与全文脱敏（提交 181b7d2、4997162）

**复现**：在 `tests/unit/system/test_logging.py` 新增用例，修改前 3 个失败——日志只有 request_id；`sk-` 密钥、邮箱、手机号、`api_key=`、Bearer 在消息与异常堆栈里原样输出；控制台是未脱敏纯文本。

**修改**
- 新增 `backend/app/core/redaction.py`：日志与 trace 共用的敏感模式与 `redact_text`。
- `backend/app/core/logging.py`：增加 `component`、`task_id`、`execution_attempt_id` 字段（ContextVar）；所有字符串字段逐段替换为 `[REDACTED]`；控制台与文件都用 JSON。
- `backend/app/modules/workflow/tasks.py`：Worker 认领后设置、`finally` 中复原两个编号。
- `backend/scripts/evaluation/render_task_trace.py`：改用共享模式。
- 一个旧测试的替身对象补 `id` 字段（未改断言）。

**验证**：`pytest tests/unit tests/scripts -q` → 908 passed / 4 skipped；Ruff 通过。

**部署检查**（第二个提交）
- 部署前确认 queued/running/retrying 为 0、两个队列长度为 0；`docker compose build` 与 `up -d --no-deps api worker report-worker beat` 均退出 0。
- 检查发现：共享日志文件里 Worker 记录 **0 条**、API 6590 条——Worker 从未调用 `configure_logging`，Celery 输出未脱敏纯文本。
- 先补失败用例 `test_celery_worker_logging_uses_project_configuration`，再在 `backend/app/core/celery_app.py` 接管 Celery 的 `setup_logging` 信号。
- 结果：909 单元/脚本、90 集成通过；4 个容器源码哈希与工作区一致；`/health/ready` 全部 ok；在 Worker 容器内写入含密钥/邮箱/手机号/密码的日志，控制台与文件均为 JSON 且全部 `[REDACTED]`，带 `task_id=999`、`execution_attempt_id=42`。
- 顺带发现：重启后旧消息重投（任务 170），Worker 判定已终态并跳过——幂等生效。
- 未验证：真实模型任务链路上的编号；uvicorn 访问日志仍为纯文本（列为待办）。

## 3. Outbox 事件卡住与重复发布（提交 ce8912f）

**现象**：12 条 Outbox 事件卡在 `broker_accepted`，对应任务都已终态；事件 163 被重复发布 1634 次，每次刷新任务 `updated_at`。

**定位过程（含被否定的假设）**
1. 假设 A“Worker 比发布确认快”与假设 B“数据库死锁”。
2. 查 Postgres 日志：0 条 `deadlock detected` → 否定 B。
3. 对比认领延迟：正常事件中位 32ms，卡住事件 1.3–1.8s。
4. 对齐时间线：任务 265/273/297 的 Worker 认领比 API 记录 `broker_accepted` 早 26–29ms → 证实 A。
5. API 日志：发消息请求 p90 约 1.35s，慢请求打开了竞态窗口。

**修改**
- `backend/app/modules/workflow/delivery/outbox.py`：`mark_analysis_task_event_worker_claimed` 可从 pending/publishing/broker_accepted 推进；新增 `settle_redelivered_analysis_task_events`。
- `backend/app/modules/workflow/lifecycle/execution.py`：认领被拒时关闭该任务的未认领事件。
- 2 个复现用例，修改前都以 `'broker_accepted' == 'worker_claimed'` 失败。

**验证**：outbox 6 项、单元/脚本 911 passed、集成 90 passed；部署后约 90 秒 12 条事件自愈（worker_claimed 141→153），发布器每轮发布 0 条。
**未验证**：新任务真实触发竞态窗口（仅单元测试覆盖）；API 慢请求原因（待办）。

## 4. 阶段 2.5：组件评测台

### 2.5.1 只读调查（提交 c3cb0fe）
- 盘点 `backend/app/modules/evaluation/` 与 42 份素材：80 条用例/56 个问题；61 条有期望路线，80 条有结果指纹，38 条有文档范围，chunk 级标注 0 条；模型调用记录不存输出。
- 产出 `docs/design/stage2_5_evaluation_survey.md`。
- 更正：调查时漏看了已有的慢测试 `tests/unit/evaluation/test_full_corpus_retrieval_evaluation.py`（按文档生成模板问题、单文档相关），在 2.5.2 中发现并复用其建索引方式。

### 2.5.2 检索评测（提交 0a087fd）
- 新增排名指标 `RankedRetrievalCase`、`evaluate_ranked_retrieval`（文档级 Hit@k、Recall@k、MRR，同一文档多个 chunk 只计一次），先写测试后实现，3 项通过。
- 新增 `backend/scripts/evaluation/run_retrieval_evaluation.py`：在 `agent_platform_test` 的一个事务里把 153 篇语料按两种切块建索引，用 19 个真实夹具问题（开发 15、留出 4）评测三种检索策略，结束时回滚，不留数据；只用本地嵌入与重排模型。
- 运行过程中的两次失败：
  1. 首跑 CPU 只有 4.7%，数据库连接“事务中空闲”，最后一条语句是向量检索——判断卡在重排模型联网检查，停止容器（事务回滚，无残留）。
  2. 改用离线模式后，嵌入模型配置的是短名 `paraphrase-multilingual-MiniLM-L12-v2`，离线时无法解析成 `sentence-transformers/...` 而失败。
  3. 最终：保持在线，但用环境变量 `RERANKER_MODEL` 指向本地快照目录，成功。
- 运行命令（仓库根目录，Git Bash）：
  `docker compose --profile evaluation run --rm --no-deps -e RERANKER_MODEL=/app/storage/huggingface/hub/models--BAAI--bge-reranker-base/snapshots/<快照> -v <backend>:/app -v <data>:/data evaluation python -m scripts.evaluation.run_retrieval_evaluation`
- 基线（建索引 218 秒）：

| 策略 | 候选 Hit@10 | 最终 Hit@3 | 最终 Recall@3 | MRR | 留出 Hit@3 | 耗时 |
|---|---|---|---|---|---|---|
| 段落 + 向量 + 重排（现行） | 0.842 | 0.789 | 0.719 | 0.789 | 0.75 | 67s |
| 段落 + 向量，不重排 | 0.842 | 0.789 | 0.719 | 0.789 | 0.75 | 0.6s |
| 段落 + 滑窗 + 重排 | 0.684 | 0.632 | 0.561 | 0.632 | 0.50 | 57s |

- 读代码定位“双切块更差”的原因：单策略路径按 `_hybrid_score`（向量 + 字符二元组重叠）排序；多策略合并后只按向量分重排，丢掉了重叠加权。记为阶段 6 待处理。
- 可复现性：第二次运行（run2）三种策略的全部指标与 run1 完全一致，只有耗时略有差异。
- 结果文件：`evaluation-runs/retrieval/20261101-baseline-run{1,2}.json`（git 忽略）。

### 3.1 任务状态机只读调查
- 迁移表集中在 `workflow/lifecycle/task_state.py`；终态只能从 running 进入，终态不可再迁移（除 awaiting_review → queued/partial）。
- 围栏：`finish_execution` / `transition_execution` 的更新条件是 `active_execution_id == 本次执行编号 AND status == 'running'`；租约恢复用 `SELECT ... FOR UPDATE`。
- 已有测试：迟到结果在租约恢复后不能发布、开始前取消被跳过、终态重投被跳过。

### 3.2 不变量测试与审计事件序号竞态（提交 6e3452a）
- 新增 `tests/integration/workflow/test_reliability_invariants.py`：
  - 运行中取消后，Worker 的迟到终态写入返回 False，任务保持 cancelled（直接通过）。
  - 4 个线程用独立数据库连接同时认领同一任务，只允许 1 个成功、只产生 1 条执行记录（首跑失败）。
- 失败原因：`append_workflow_event` 用“当前最大序号 + 1”，多个被拒的投递同时给获胜执行追加 `execution_claim_rejected`，触发唯一约束，落败 Worker 抛异常而不是返回“已认领”。
- 修复：在保存点（savepoint）里插入，冲突时只回滚这一条并重试，最多 5 次；没有用行锁（见决策 D10）。
- 验证：撤掉修复 3/3 失败，加上修复 3/3 通过；单元/脚本 919 passed、集成 92 passed。

### 3.3 重试分类与退避抖动（提交 124cbf1）
- 发现：两处 `countdown=2 ** (retries + 1)` 无抖动；所有 `OSError` 都可重试，包括 PermissionError、FileNotFoundError。
- 修改：`_retry_countdown`（基数 × [0.5, 1.5] 随机系数）；`_PERMANENT_OS_ERRORS` 排除 4 类永久系统错误。
- 新增 `tests/unit/workflow/test_retry_policy.py` 12 项；单元/脚本 931 passed、集成 92 passed。

### 3.4 超时与步数预算（提交 af73445）
- 盘点已有：LLM 30s 超时、SQL statement_timeout、RAG 数据库超时、单任务模型预算、路由外部重试上限 2、图步数上限 20。
- 新增 `tests/integration/workflow/test_step_budget.py`：路由死循环被步数上限截断；Worker 遇步数耗尽进入 failed 且不调用重试。2 项直接通过。
- 未做：任务级墙钟截止时间（见决策 D12）。

### 2.5.3 报告校验拦截评测（提交 77a01f7）
- 新增 `backend/app/modules/evaluation/report_gate.py`：11 种报告篡改 + 4 种数字篡改；1 份合法报告 + 3 条合法数字表述作对照。
- 首版因样例字段写错出现“假拦截”（被缺字段拦下而非目标规则）；修正样例并为每个篡改登记预期原因，原因不符不计拦截。
- 结果：15/15 拦截，对照误拦 0/4；单元/脚本 919 passed / 4 skipped。
- 局限：合法的派生数值（如模型自算的环比）会被数字校验拦截。

### 2.5.4 录制回放网关（提交 21b8e44）
- 新增 `backend/app/core/gateway/replay.py`：record 按请求哈希落盘（临时文件 + 原子替换）；replay 缺失即 `ReplayMissError`，不回落付费调用。
- 未接入生产网关工厂；4 项单元测试通过。

### 2.5.5 Planner 路由组件评测（用户批准付费录制）
- 发现：没有任务上下文时，模型治理层不计费也不登记，所以评测脚本必须自带费用上限。
- 新增 `backend/scripts/evaluation/run_planner_route_evaluation.py`：
  - `BudgetGuardGateway`：每次调用前按“输入 token + 预留 512 输出 token”预估最坏费用，超过调用上限（80 次）或费用上限（$0.08）就拒绝调用；
  - 三种模式：local（免费模拟，用来检查脚本）、record（真实模型 + 录音）、replay（只读录音）。
- 范围：39 个有期望决策的不重复问题（开发 32、留出 7）；SQL 结果评测需要 Data Agent 的完整运行时，拆为 2.5.6。
- 执行顺序：local 空跑（39 次调用、脚本正常）→ 核对实际模型与价格表一致（只输出真假，不输出配置值）→ 付费录制 → 回放。
- 录制结果：40 次调用（1 次修复重试），预估 $0.0237（未经供应商账单核对）；准确率 64.1%（开发 65.6%，留出 57.1%）。
- 回放：0 次调用，逐条结果与录制完全一致。
- 14 个错判的人工归类（未修改任何标签）：
  - 5 个是端到端故障注入场景题（如“审核节点暂时失败后应如何重新生成报告？”），作为路由题不合适；
  - 6 个两种决策都说得通（如“某新产品”被要求澄清、hybrid 与 data_only 之争）；
  - 3 个是明确的 Planner 错误（如“销售额下降能否直接证明唯一原因？”被直接回答）。
- 未验证：Planner 之后的“计划语义复核”节点会纠正多少；生产链路里的上下文对路由的影响。

### 2.5.5b 路由专用标签集（2026-11-01 用户已确认规则）
- 新增 `backend/tests/fixtures/evaluation_routing/planner_routes_v1.json`，原夹具未改。状态 `pending_user_review`。
- 先写规则再逐题套用：R1–R4 来自 Planner 系统提示；A1（需要数据但缺时间→也接受澄清）、A2（未指明的“某X”→也接受澄清）、A3（具体指标的方法题→data_only 与 hybrid 都接受）；E1（系统故障恢复场景题→不计分）。
- 一致性复查：发现 #21、#12 符合 A1/A3 但漏标，补上（包括模型本来答对的题）。最终放宽 11 题、排除 5 题，原标签始终在可接受列表首位。
- 回放重算（0 次调用）：34 题 88.2%（开发 89.3%，留出 83.3%）；原标签 64.1% 保持不变。
- 仍错 4 题：两题把“分析方法问题”当成直接回复；一题坏账判断只查数据；一题不存在区域被要求澄清。
- 已知偏差：标注者看过一次模型输出，放宽规则可能偏向模型答案；新增 2 项单元测试检查“原标签在首位、每题有规则编号”。

### 3.5 主环境故障演练（用户批准方案 A，2026-11-02）
- 方案与完整结果表：`docs/design/stage3_5_game_day_plan.md`。新增 `backend/scripts/evaluation/drill_client.py`（API 容器内提交/取消任务，一次性租户，凭据不输出）。
- 过程中的工具问题：httpx 客户端登录后又进入 `with` 块导致“不能打开两次”，改为 finally 关闭（未提交任务、未花钱）；重建 API 容器会丢失拷进去的脚本，每次重建后重新拷贝。
- 结果：基线 + 8 项，7 项达到期望；数据库重启导致任务直接 failed 不重试（另立 3.6）；超时演练第一次无效，因为超时在 API 受理时冻结进任务，改为 API 与 Worker 同时覆盖后生效。
- 费用：37 次调用，最坏 $0.0306（已结算 $0.020452 + 未知按预留 $0.010142），上限 $0.10。
- 恢复：13 服务、1 Worker、readiness ok、无进行中任务与未认领 Outbox、超时恢复 30 秒。

### 3.6 数据库短暂中断的重试分类
- 新增 `backend/app/db/errors.py`：`is_transient_database_error` 沿异常链（最多 8 层）找根因——OperationalError、InterfaceError、连接失效视为短暂；IntegrityError、ProgrammingError、根因不明的 PendingRollbackError 不算。
- `workflow/tasks.py` 的 `_is_retryable_exception` 先调用它；`planner_agent.py` 的兜底捕获遇到短暂数据库错误改为向上抛。
- 测试 `tests/unit/workflow/test_transient_database_errors.py` 共 11 项：第一版 8 项（撤掉修改 4 项失败）；复测发现真实链路是“OperationalError → PendingRollbackError”，补 3 项（修改前 2 项失败）。
- 验证：单元/脚本 947 passed、集成 94 passed；部署后演练 4d 通过。
- 教训：第一次修复只看了“应该抛什么异常”，没看“实际抛的是什么异常”；复测把差异暴露出来。

## 5. 阶段 4：工具层与 SQL 防线（2026-11-02，用户授权自主推进）

- 阶段 3 验收：本地标签 `stage-3-done`（阶段 2 出口验收与标签尚未做）。

### 4.1 只读调查（`docs/design/stage4_tool_sql_survey.md`）
- 工具运行时：白名单、schema 校验、每次重新鉴权、范围校验、服务端注入超时、调用预算、调用前后审计均具备。缺口：多余参数被静默丢弃；所有拒绝返回同一句话。
- 计划要求对照的教学版 `tool_layer.py` 在仓库中不存在。
- 执行层只读核对：分析账号 `acme_readonly` 非超级用户、不能绕过行级安全、0 个写权限、不能执行 `pg_read_file`/`lo_import`；连接与事务均只读，带语句超时。

### 4.3/4.4 AST 层加固（提交 65927c8，已部署）
- 先离线探测：用真实业务表名后，CTE 内 DELETE、FOR UPDATE、pg_sleep、pg_read_file、set_config、lo_import 等都能通过 AST。（第一次探测用了不存在的表名 `orders`，被表检查拦下，结论无效——换真实表名重测。）
- 收集历史上模型真实生成的 45 条不同 SQL 作为误拦回归样本（只用到 sum/count/round/coalesce/nullif/cast/case/日期格式化）。
- 新增 `tests/unit/analysis/test_sql_adversarial.py`：54 条攻击 + 45 条历史 SQL；修改前 27 条攻击通过，修改后 100 项全过。
- 修改 `sql_validator.py`：遍历整棵语法树，拒绝写入/结构修改节点、行锁、`pg_`/`lo_`/`dblink`/`txid_` 前缀及 set_config/current_setting/query_to_xml 等函数。
- 验证：单元/脚本 1047 passed、集成 94 passed；部署后真实任务 311 completed（$0.00332）。
