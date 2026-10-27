# 项目交接盘点

- [已验证] 盘点日期：2026-10-27（America/New_York）；工作目录：`C:\Users\qyf21\Desktop\1\Agent项目学习`。本次 `git rev-parse HEAD` 为 `2dd52ab3df02401625c05229811f5862a3a0d436`。
- [已验证] 盘点开始及写报告前，`git status --short` 均只有 `?? artifacts/`；`git diff --stat`、`git diff --cached --stat` 均无输出。未跟踪目录不属于 HEAD，不应把其中产物自动视为当前提交的结果。
- [已验证] 本报告的源码判断来自本次文件读取/AST 检查；历史数字来自本次打开的带日期文档，只证明文档有该记录，不表示本次重跑。证据命令及口径见下表。
- [未验证] 未读取 `.env` 或实际凭据；配置有效值、数据库中的真实数据和运行中容器的代码版本未知。报告不提供任何凭据值，凭据占位统一为 `***`。

| 证据编号 | 本次实际执行的命令/操作及范围 |
|---|---|
| G1 | [已验证] `git -c core.quotePath=false log --oneline --since="8 weeks ago"`；随后用 `git log --since="8 weeks ago" --format="%h %as %s"` 补充日期。 |
| G2 | [已验证] `git -c core.quotePath=false log -15 --stat`，最近 15 次提交逐项列于 E。 |
| G3 | [已验证] `git status --short`、`git diff --stat`、`git diff --cached --stat`、`git rev-parse HEAD`。 |
| G4 | [已验证] Python `subprocess.check_output(['git','-c','core.quotePath=false','log','--since=8 weeks ago','--format=','--name-only'])`；对非空文件路径用 `collections.Counter` 计数，取 `most_common(20)`。 |
| S1 | [已验证] Python `pathlib.Path.rglob` 枚举文件，`read_text(encoding='utf-8-sig').splitlines()` 数物理行；源码扩展名 `.py/.ts/.tsx/.css/.sql`，排除 `__pycache__`，不含依赖、缓存或 `.env`。 |
| S2 | [已验证] `rg --files -g AGENTS.md -g '!node_modules' -g '!.venv'`；Python 对 `AGENTS.md`、`docs/plans/**/*.md`、`docs/**/*.md` 计数；统计时尚未创建本报告。 |
| E1 | [已验证] `docker ps --format "{{.Names}}|{{.Status}}|{{.Ports}}"` 与 `docker ps -a --format "{{.Names}}|{{.Status}}"`，没有读取容器环境变量或日志。 |
| E2 | [已验证] `python --version`、`node --version`、`npm --version`、`python -m ruff --version`；`Test-Path .venv/Scripts/python.exe`、`Test-Path frontend/node_modules`。 |
| T1 | [已验证] backend 目录执行 README 原 lint 命令 `..\.venv\Scripts\python.exe -m ruff check app tests`，解释器不存在，命令未进入 Ruff。 |
| T2 | [已验证] backend 目录设置 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONUTF8=1` 后，执行 `python -m ruff check --no-cache app tests`，退出 1，8 条 E402。 |
| T3 | [已验证] frontend 目录设置 `npm_config_logs_max=0` 后，执行 `npm test -- --no-cache --configLoader native`，退出 0，2 个测试文件、7 项测试通过。 |
| D1 | [已验证] 本次按修改时间枚举 `docs/**/*.md`，最新为 `docs/evidence.md`；直接读取其中 2026-10-27 最新条目及 `docs/design/evaluation_baseline.md`。 |

## A. 项目与当前端到端可运行性

- [已验证] 这是一个接收自然语言经营问题、按公司范围查询经营库和文档、经审核与确定性检查后把结构化报告写入任务记录的应用。依据：`README.md:5`、`backend/app/modules/conversations/api.py:306`、`backend/app/modules/workflow/tasks.py:354`。
- [已验证] 本次观察到的默认本机部署无法直接作为端到端验证环境：主项目 PostgreSQL、Redis、三套经营库、前端容器均退出，`agent-api-1` 显示 `Restarting (3)`。卡点已在 API/数据库/队列基础设施层出现，尚未进入问题分析；依据 E1。
- [未验证] 没有发送经营问题，没有验证 HTTP 健康检查、模型调用或报告写库；不能断定源码在准备齐全的独立环境中也无法运行。API 重启的准确原因未知，本次未读容器日志。
- [已验证] 文档记录 2026-10-27 的四个知识案例经过 API→队列→Worker→模型/检索→发布，其中三个为 `published`、一个为 `published_partial`；这是历史记录，不是当前运行状态。依据：`docs/evidence.md:3544`、`:3548`、`:3551`。
- [未验证] 不提供“本次验证可用”的启动步骤。现有启动入口是 `README.md:68` 和 `docs/operations/single_node_runbook.md`；接手者需先核对配置、数据源与迁移，不能仅凭 Worker 容器处于 Up 就认定链路可运行。

## B. 模块清单

- [已验证] 表中“文件/行数”为 S1 的源码文件数/物理行数，包含注释、空行、测试以外的源码；不是逻辑代码行。14 个业务模块合计 177 文件、26452 行。
- [未验证] 除前端所测契约外，本次未运行模块级测试；“未验证”表示运行能力未知，不表示该模块没有实现。“有已知缺陷”仅指所列检查/历史现象，不泛化为全部能力不可用。

| 模块名 | 作用 | 关键文件 | 文件/行数 | 状态 | 证据 |
|---|---|---|---:|---|---|
| analysis | 计划、Schema、SQL、指标与结果契约 | `backend/app/modules/analysis/data/data_agent.py` | 29 / 3138 | 有已知缺陷 | [已验证] S1；`data_agent.py:96`；历史数据案例仍失败见 `docs/evidence.md:3574`，当前是否复现未验证。 |
| conversations | 会话、消息、冻结任务范围、Outbox 创建 | `backend/app/modules/conversations/service.py` | 6 / 1257 | 未验证 | [已验证] S1；该文件 `:160`、`:233`、`:247`。 |
| documents | 文档文本 CRUD、异步处理、分块 | `backend/app/modules/documents/service.py` | 13 / 1131 | 未验证 | [已验证] S1；该文件 `:12`、`:47`；上传路由未挂载见 `backend/app/api/router.py:19`。 |
| evaluation | 持久化 Observation、分类评分、阈值 | `backend/app/modules/evaluation/observation.py` | 9 / 2844 | 未验证 | [已验证] S1；该文件 `:236`、`:427`；`business.py:614`、`:818`。 |
| identity | 登录身份与认证依赖 | `backend/app/modules/identity/authentication.py` | 5 / 371 | 未验证 | [已验证] S1；该文件 `:55`、`:74`。 |
| input_artifacts | 附件上传、隔离、处理、版本契约 | `backend/app/modules/input_artifacts/api.py` | 28 / 6438 | 未验证 | [已验证] S1；`backend/app/api/router.py:19` 说明上传路由不挂载；这是主动冻结，不计作故障。 |
| knowledge | 文档检索、Embedding、Reranker、知识证据 | `backend/app/modules/knowledge/agent.py` | 14 / 1173 | 未验证 | [已验证] S1；该文件 `:36`；`tool.py:50`、`:86`。 |
| memory | Planner 记忆选择与报告记忆保存 | `backend/app/modules/memory/service.py` | 4 / 250 | 未验证 | [已验证] S1；该文件 `:34`、`:123`。 |
| observability | 健康检查、任务指标、拒绝审计 | `backend/app/modules/observability/health_service.py` | 9 / 371 | 未验证 | [已验证] S1；该文件 `:10`；健康路由在 `backend/app/api/router.py:12`。 |
| organizations | 公司/角色授权、经营数据源与快照 | `backend/app/modules/organizations/access.py` | 7 / 1474 | 未验证 | [已验证] S1；该文件 `:28`、`:66`；数据源使用见 `conversations/service.py:219`。 |
| reporting | 报告组织、语义复核、数字/引用校验 | `backend/app/modules/reporting/reviewer_agent.py` | 11 / 1697 | 未验证 | [已验证] S1；该文件 `:252`、`:263`；`validation.py:14`。 |
| reviews | 人工审核队列、批准与拒绝 | `backend/app/modules/reviews/service.py` | 5 / 359 | 未验证 | [已验证] S1；该文件 `:29`、`:43`、`:96`。 |
| runtime | 工具授权、范围、预算、审计适配 | `backend/app/modules/runtime/tool_runtime.py` | 4 / 991 | 未验证 | [已验证] S1；该文件 `:83`、`:349`。 |
| workflow | Worker、图编排、执行权、检查点、发布 | `backend/app/modules/workflow/tasks.py` | 33 / 4958 | 有已知缺陷 | [已验证] S1、T2；`models.py:256` 等有本机 lint 报错，版本限制见 F。 |
| API 组装 | 挂载领域路由 | `backend/app/api/router.py` | 2 / 20 | 未验证 | [已验证] S1；该文件 `:11`。 |
| core | Settings、日志、异常、模型网关、Celery | `backend/app/core/settings.py` | 14 / 1635 | 未验证 | [已验证] S1；该文件 `:18`；`logging.py:64`。 |
| db | 数据库会话与基础设施 | `backend/app/db/session.py` | 4 / 105 | 未验证 | [已验证] S1；测试导入入口 `backend/tests/conftest.py:16`。 |
| utils | 公共工具 | `backend/app/utils/` | 1 / 164 | 未验证 | [已验证] S1 目录统计；本次没有逐项核验工具行为。 |
| frontend/src | React 工作台及 API 客户端 | `frontend/src/App.tsx`、`api.ts` | 10 / 1248 | 部分可用 | [已验证] S1、T3：仅两个测试文件的七项契约；页面联调、构建未验证。 |

## C. API 到报告写库的主链

- [已验证] 以下是当前源码调用链，不是本次执行 trace。路径以 `backend/app/` 为根；存在分支、重试与人工审核，不是每个问题都依次经过全部 Agent。依据：`modules/workflow/orchestration/graph.py:42`、`:70`、`:78`。

| 步骤 | 函数 → 函数及位置 | 传递/写入字段与边界 |
|---|---|---|
| 1 | [已验证] `api/router.py:15` → `create_conversation_message_endpoint`，`modules/conversations/api.py:306`；授权依赖 `require_analysis_permission`，`modules/organizations/access.py:66` | HTTP 输入 `conversation_id/content/document_ids/artifact_version_ids`；服务端提供 `CurrentCompanyContext` 与 `request_id`。 |
| 2 | [已验证] endpoint `:314` → `create_conversation_task_service`，`modules/conversations/service.py:160` | 核对会话归属，文档须为当前公司、已处理且角色可见；未指定文档时冻结允许集合，越权选择抛错；`:178`–`:192`。 |
| 3 | [已验证] service `:201` → `create_message`；`:214` → `build_conversation_context`；`:219` → `get_data_source`；`:226` → `get_snapshot` | 写用户消息并形成历史上下文；数据源/快照不存在时抛错并回滚。该检查也发生在 Planner 判断纯知识路线之前。 |
| 4 | [已验证] service `:233` → `create_task`，`modules/workflow/repository.py:63`；`:247` → `create_analysis_task_event`，`modules/workflow/delivery/outbox.py:31` | 持久化 `user_id/company_id/question/conversation_id/input_message_id/context_snapshot/data_source_id/schema_snapshot_id/document_ids/input_artifact_version_ids/request_id`；Outbox payload 只有 `task_id`。 |
| 5 | [已验证] service `:248` → assistant 消息，`:257` → `db.commit()`；endpoint `:342` → `publish_analysis_task_event`，`delivery/outbox.py:43` | 用户消息、任务、Outbox、assistant 占位在服务事务提交后才尝试投递；投递失败保留待重试事件。 |
| 6 | [已验证] Outbox `:50` → `claim_analysis_task_event_for_publication`，`:125`；`:68` → `process_analysis_task.delay(task_id=...)` | 事件投递认领与消息 broker 确认分开；Celery 传任务 ID，不传用户生成的权限对象。 |
| 7 | [已验证] `process_analysis_task`，`modules/workflow/tasks.py:511` → `_claim_task`，`:304` → `claim_execution`，`lifecycle/execution.py:256` | 输入 `task_id/celery_task_id/worker_id`；原子认领 queued/retrying，形成 attempt、execution_id、租约和可恢复检查点；认领不到即返回。 |
| 8 | [已验证] Worker `tasks.py:533` 设置租户；`:595`–`:629` 组装 `ToolRuntime` 与数据源/Schema；`:640` → `run_analysis`，`orchestration/graph.py:173` | 从持久化记录恢复 `question/user_id/company_id/context_snapshot/document_ids`，传记忆、附件上下文、租约/阶段/检查点回调及 `resume_state/resume_next_node`。 |
| 9 | [已验证] `run_analysis` `graph.py:263` → `workflow.invoke`；图入口 → `planner_node`，`nodes.py:144` → `PlannerAgent.run`，`analysis/planner/planner_agent.py:35` → `PlanningService.decide`，`planning.py:328` | 问题、上下文、记忆等生成 `plan/planner_result/planner_outcome/scope_fingerprint`；非法计划进入失败分支。 |
| 10 | [已验证] `planner_semantic_review_node`，`nodes.py:231` → 图路由 `graph.py:42` | 根据 `plan.action/route` 分流 data_only、hybrid、knowledge_only 或澄清/拒绝/直接回应；本次未验证实际模型决策。 |
| 11 | [已验证] `data_node`，`nodes.py:509` → `DataAgent.run`，`analysis/data/data_agent.py:96` → SQL 生成 `:132`、指标检查 `:279`、包装工具 `:310` | 传问题、计划、Schema、数据源；要求候选 SQL 与 `query_contract`；回写列/行、结果评估、事实与证据。 |
| 12 | [已验证] `RuntimeTool.execute`，`runtime/tool_runtime.py:57` → `ToolRuntime.execute`，`:349` → `SQLTool.execute`，`analysis/data/sql_tool.py:36` → `execute_readonly_sql`，`sql_executor.py:94` | Runtime 复核当前授权、输入、冻结范围、文档权限和预算；SQL 在 `sql_executor.py:104` 做 AST 校验，`:121` 设置只读事务，`:130` 执行；结果再经过 `data_agent.py:317`、`:322` 的业务契约检查。 |
| 13 | [已验证] hybrid 分支 `graph.py:70` → `knowledge_node`，`nodes.py:414` → `KnowledgeAgent.run`，`knowledge/agent.py:36` → 包装 RAG 工具 `:69` | 输入 `question/confirmed_facts/company_id/document_ids`；形成检索 brief，写 `knowledge_result`。合法冻结空范围由 `runtime/tool_runtime.py:83` 处理，不扩大检索范围。 |
| 14 | [已验证] Runtime → `RAGTool.execute`，`knowledge/tool.py:50` → `retrieve_evidence`，`rag/retrieval.py:11` → `search_similar_chunks`，`:63` | 查询嵌入、公司/文档过滤、向量召回和配置的重排；工具返回证据或不足状态；实际缓存、模型和数据库均未在本次验证。 |
| 15 | [已验证] `reviewer_node`，`nodes.py:700` → `ReviewerAgent.run`，`reporting/reviewer_agent.py:252` → `compose_report`，`composer.py:36`；语义复核在 `reviewer_agent.py:276` | 输入计划、数据/知识证据，形成 `review_result/report/answer_validation/final_answer`；Reviewer 不是最终写库授权者。 |
| 16 | [已验证] `smart_router_node`，`nodes.py:792` → `choose_next_action`，调用点 `:795` → 条件边 `graph.py:78` | 根据证据、校验和重试状态决定 stop/retry/replan；纯知识 ready 分支在 `orchestration/router.py:120`；返回 `terminal_result/loop_stop_reason` 等。 |
| 17 | [已验证] Worker `tasks.py:671` → `_save_workflow_result`，`:354` → `validate_report`，`reporting/validation.py:14` → `decide_completion`，`lifecycle/publication.py:35` | 再检报告结构与冻结引用范围，写 `deterministic_validation` 与 `publication`；待人工审核保存 `report_draft`，不得把它当已发布报告。 |
| 18 | [已验证] `_save_workflow_result` `:438` → `finish_execution`，`lifecycle/execution.py:566` → `db.commit()`，`:656` | 仅更新 task_id、active_execution_id、running 状态仍匹配的记录；写 `status/result_summary/result_data/completed_at`，追加检查点和执行事件。报告位于 `analysis_tasks.result_data.report`，依据 `workflow/models.py:29`、`:154`、`:155`。 |
| 19 | [已验证] `_save_workflow_result` `:451` → `persist_report_memory`；`:459` → `_sync_assistant_message`；`:465` → 第二次提交 | 已发布结果之后再保存记忆及会话展示。人工审核批准另走 `tasks.py:468` 的 `_publish_approved_draft`，重做报告校验后调用相同执行权写入函数。 |

## D. 已知缺陷与阻断项（按进入主链的先后）

### 1. 本次环境缺少运行中的主依赖

- [已验证] 现象/复现：执行 E1，平台 PG、Redis、经营库、前端均 Exited，API Restarting；期望是依赖在线且 API 可服务，实际不满足。影响：请求接入、任务持久化、投递与 SQL；相关配置位置 `docker-compose.yml:31`、`:90`、`:173`、`:353`。
- [推测] 依赖退出可能导致 API 重启；[未验证] 未读错误日志，不能确定重启根因，也未证明其他地址是否存在替代服务。

### 2. README 的后端验证解释器路径不存在

- [已验证] 现象/复现：T1 返回命令不存在，`Test-Path .venv/Scripts/python.exe` 为 False；期望进入 lint，实际未启动 Python。相关文件：`README.md:146`、`:147`；影响：接手者按文档运行后端检查。
- [未验证] 虚拟环境为何缺失、其他解释器是否具备完整锁定依赖未知；未安装依赖或创建虚拟环境。

### 3. 后端测试入口与此次只读/不读配置限制冲突

- [已验证] 现象/静态复现：`backend/tests/conftest.py:16`–`:17` 导入 session/app；`backend/app/core/settings.py:20` 指向 `.env`；`backend/app/main.py:46` 配置日志，`core/logging.py:64`、`:77` 创建目录和日志。测试 fixture 在 `conftest.py:33` 执行迁移。
- [未验证] 期望在本次约束下获得测试结果，实际未启动 pytest。根因不是已证实的业务异常，而是测试启动副作用和依赖条件不符合本次限制；影响所有需要该 conftest 的验证。

### 4. 本机替代 lint 报 8 条 E402

- [已验证] 现象/复现：T2；期望 lint 无诊断，实际退出 1。报错在 `backend/app/modules/workflow/models.py:256`、`:257`、`:258`、`:259`、`:260`、`:261`、`:262`、`:265`，均为模块级 import 不在文件顶部；影响静态检查。
- [已验证] `models.py:254` 注释说明这些导入用于注册 ORM 关系目标；本机 Ruff 是 0.15.22，项目在 `backend/pyproject.toml:35` 声明 0.16.1。
- [未验证] 未在项目声明版本下重跑，不能把此结果等同于当前 CI 失败，也不能据此直接移动导入而忽略循环依赖。

### 5. 历史单月营业收入案例仍有失败记录

- [已验证] 现象：2026-10-27 台账仍列 `data-east-delivered-revenue-2025-08`，`violation=outcome_correct`，`sql_result_equivalent` 未知；期望匹配开发 fixture，历史记录未满足。依据：`docs/evidence.md:3574`。
- [未验证] 本次未复现；复现方向是在隔离依赖环境对同一开发 case 运行准备/执行/Observation 评分，而不是修改期望。确切根因未知；相关链：`analysis/data/data_agent.py:96`、`evaluation/observation.py:236`、`evaluation/business.py:614`；影响 SQL 业务回答及评分，不证明 AST 或只读隔离失败。

### 6. 当前执行顺序的文档入口互相指向不同计划

- [已验证] 现象/复现：比较 `AGENTS.md:3`–`:5` 与路线图 `docs/plans/single_node_production_style_ai_application_roadmap.md:5`；前者指定 improvement 计划，后者仍将本期执行指向 history/core-first。期望入口一致，实际读者会遇到两套指向；影响接手规划和规则解释。
- [已验证] `AGENTS.md:5` 明确新顺序优先并将旧计划降为历史；本次按它解释，没有修改任何规则文件。

### 7. 最新评测记录的版本引用有本地解析缺口

- [已验证] 现象/复现：`git cat-file -t 6cd77119` 返回 `Not a valid object name`；该编号出现在 `docs/evidence.md:3573`。期望能从旁录定位源码，实际本地该对象不可解析；影响旧评测到当前源码的追溯。
- [推测] 最新提交标题含 history rewrite，可能与此有关，但标题不能证明改写过程；[未验证] 未查询远端、reflog 或其他 clone，不断言提交永久丢失。作为对照，`git cat-file -t e0641bc6`、`git cat-file -t bc841d82` 本次都返回 commit。

## E. 近几周工作回顾

- [已验证] G1 当前可见时间窗中有 43 次提交，日期从 2026-09-14 至 2026-10-27；这是当前 Git 可达历史，不是曾经存在过的所有本地工作记录。

| 主题 | 当前历史中的记录 | 可作出的事实判断 |
|---|---|---|
| 目录调整 | [已验证] `c7683cf`（09-14）；`3904ec6`、`3b9a6e5`、`684eea1`（10-19）；G1 | [已验证] 存在清理、调整前快照、目录重排和镜像验证记录；标题不是全模块行为验证。 |
| 工程检查与边界整理 | [已验证] 10-24 的 `188f647/f547e0e/3aed645/e5481bb/30c58df/2326e42/b9614ea/3844f6f`；G1 | [已验证] 提交主题覆盖静态检查、workflow、API、附件契约、脚本与 CI；本次只重跑 F 中的检查。 |
| CI 演练及回退 | [已验证] `433d532→13c3a1f`、`b857e54→b9f11e0`；G1 及 `git show --stat` | [已验证] 两次故障/门禁注入后各有显式 Revert；对 `.github/workflows/ci.yml` 比较每次注入前到对应回退后均无差异，不能将演练注入描述为业务修复失败。 |
| 上传冻结 | [已验证] `01c741a`（10-25）；当前 `backend/app/api/router.py:19` | [已验证] 文件与附件上传入口未挂载，旧契约留在隔离测试应用；不是功能意外消失。 |
| 开发评测契约 | [已验证] 10-26 的 `f48ab58/37dd408/e3eb5f6/9dfba77/d923fc9/cb84cbb/7ba6f2e`；G1 | [已验证] 涉及候选清单、文本准备、来源限定、oracle、专用探针选择、非有限费用输入。 |
| 知识失败及修正 | [已验证] `127a84b→956314a→f8fda63→ac05069`；G1、`docs/evidence.md:3492`、`:3548` | [已验证] 历史先记录知识成功路径终止失败及空范围拒绝，后有路由/Runtime 修改和四例对照记录；未发现这些修复被上述两个 CI Revert 撤销。 |
| 评测补证与汇总 | [已验证] `acaab39/936b9f9/4d37326/482d553`；G2 | [已验证] 这些提交主要写证据/设计文档，不应计作新增业务实现。 |
| 样例数据说明 | [已验证] `2dd52ab`；G2 | [已验证] README、语料 README、生成器三处加入/同步说明，共 11 行增加、1 行删除。 |

### 最近 15 次提交改动文件

| 提交 | 文件（G2） |
|---|---|
| `2dd52ab` | [已验证] `README.md`；`backend/scripts/data/generate_business_data.py`；`data/business_knowledge_base/README.md`。 |
| `482d553` | [已验证] `docs/design/evaluation_baseline.md`；`docs/evidence.md`。 |
| `4d37326` | [已验证] `docs/evidence.md`。 |
| `ac05069` | [已验证] `docs/evidence.md`。 |
| `936b9f9` | [已验证] `docs/evidence.md`。 |
| `acaab39` | [已验证] `docs/evidence.md`。 |
| `f8fda63` | [已验证] `backend/app/modules/runtime/tool_runtime.py`；`backend/tests/unit/runtime/test_tool_runtime.py`；`docs/design/evaluation_baseline.md`；`docs/evidence.md`。 |
| `956314a` | [已验证] `backend/app/modules/workflow/orchestration/router.py`；`backend/tests/unit/workflow/test_workflow_router.py`；`docs/evidence.md`。 |
| `127a84b` | [已验证] `docs/evidence.md`。 |
| `b415684` | [已验证] `docs/evidence.md`。 |
| `87c215d` | [已验证] `docs/evidence.md`。 |
| `2c5f385` | [已验证] `docs/design/evaluation_baseline.md`；`docs/evidence.md`。 |
| `b10b857` | [已验证] `docs/design/evaluation_baseline.md`；`docs/evidence.md`。 |
| `7c7e436` | [已验证] `docs/evidence.md`。 |
| `7ba6f2e` | [已验证] `backend/scripts/evaluation/prepare_business_evaluation.py`；`backend/tests/scripts/test_prepare_business_evaluation.py`；`docs/design/evaluation_baseline.md`；`docs/evidence.md`。 |

### 最近八周修改频次前 20

- [已验证] G4 按每条非空 name-only 记录计数，包括新增/删除，不按行数加权、不跨重命名合并，也不计未提交修改；同频按 Git 输出先后排列。

| 文件 | 次数 |
|---|---:|
| [已验证] `docs/evidence.md` | 29 |
| [已验证] `docs/design/evaluation_baseline.md` | 11 |
| [已验证] `backend/tests/scripts/test_prepare_business_evaluation.py` | 6 |
| [已验证] `CONTRIBUTING.md` | 6 |
| [已验证] `.github/workflows/ci.yml` | 6 |
| [已验证] `backend/app/modules/runtime/tool_runtime.py` | 5 |
| [已验证] `README.md` | 4 |
| [已验证] `backend/scripts/evaluation/prepare_business_evaluation.py` | 4 |
| [已验证] `backend/app/modules/input_artifacts/outbox_tasks.py` | 4 |
| [已验证] `backend/app/modules/input_artifacts/tasks.py` | 4 |
| [已验证] `backend/app/modules/evaluation/business.py` | 4 |
| [已验证] `backend/app/modules/evaluation/business_schemas.py` | 4 |
| [已验证] `backend/app/modules/reporting/numeric_validation.py` | 4 |
| [已验证] `backend/app/modules/reporting/semantic_review_service.py` | 4 |
| [已验证] `backend/app/modules/conversations/api.py` | 4 |
| [已验证] `backend/app/modules/conversations/service.py` | 4 |
| [已验证] `backend/app/modules/observability/repository.py` | 4 |
| [已验证] `backend/app/modules/reviews/service.py` | 4 |
| [已验证] `backend/tests/integration/conversations/test_conversations.py` | 4 |
| [已验证] `backend/app/modules/workflow/models.py` | 4 |

- [未验证] 除上述精确比较的 CI 回退与有日期的案例对照外，本次未逐提交证明其他修复“无效”或“改回”；高修改频次本身不能证明返工。

## F. 测试与评测现状

| 类别 | 本次静态清点 | 本次运行结论 |
|---|---|---|
| 后端 unit | [已验证] S1：96 个源码文件，22469 行。 | [未验证] 未运行；目录名不保证没有数据库 fixture。 |
| 后端 integration | [已验证] S1：18 个源码文件，4918 行。 | [未验证] 未运行，主项目服务未启动。 |
| 后端 scripts | [已验证] S1：8 个源码文件，914 行。 | [未验证] 未运行。 |
| 后端 tests 合计 | [已验证] S1：124 个源码文件，28402 行，含顶层 conftest 等；不含 JSON fixture。 | [未验证] 没有 pytest 收集数量、通过数、失败数或失败测试名；均为未知，不能填 0。 |
| e2e | [已验证] `backend/tests/integration/workflow/test_celery_e2e.py:21`；`integration/input_artifacts/test_local_object_storage_e2e.py:47`；`integration/conversations/test_conversations.py:340` 有标记。 | [未验证] 按任务要求不运行。 |
| slow | [已验证] `backend/tests/integration/documents/test_document_tasks.py:124`；`unit/evaluation/test_full_corpus_retrieval_evaluation.py:43` 有标记。 | [未验证] 按任务要求不运行。 |
| 后端 lint 原命令 | [已验证] T1：命令执行失败，未启动 Ruff。 | [未验证] README 指定环境的 lint 结果未知。 |
| 后端 lint 替代命令 | [已验证] T2：Ruff 0.15.22，退出 1，共 8 条 E402，位置见 D4。 | [已验证] 这是本机版本结果，未使用 `--fix`，未生成 Ruff 缓存。 |
| 前端 npm test | [已验证] T3：Vitest 4.1.10，退出 0；2 files passed、7 tests passed、0 failed，耗时 23.13 秒。 | [已验证] 测试文件为 `frontend/src/api.test.ts`、`frontend/src/DocumentPage.test.tsx`；无失败测试名或失败错误摘要。 |

- [已验证] 前端沿用 `frontend/package.json:10` 的 `vitest run`，仅加 `--no-cache --configLoader native`；读取已安装 Vite/Vitest 实现确认这些选项存在，前端目录只枚举到 `.env.example`，没有读取它。实际测试包含 HTTP 客户端 mock 与文档表单交互，不是真实后端联调。
- [未验证] README 的 `pytest tests -q -m "not e2e and not slow"` 未运行：指定解释器不存在、平台 PG/Redis 已退出，且测试入口读取 `.env`、创建日志并执行迁移；没有为绕开这些问题安装依赖或改测试。
- [已验证] 最新带日期评测记录为 `docs/evidence.md:3571` 的 2026-10-27 交叉核验：文档记载 23 项中 21 项有评分，合并记录为 20 pass / 1 fail / 2 未执行；任务类 8/10 有记录，其中 7 pass / 1 fail，专用权限/可靠性类 13/13 记为 pass。依据 `:3573`–`:3575`；这些不是本次测试结果，也不是同一代码版本的成功率。
- [已验证] 统一冻结的当前评测基线：在本次检查的台账与设计稿中不存在；设计稿标记尚未冻结，台账仍为 `proposed_not_frozen`，23 项 `oracle_review` 均 pending。依据 `docs/design/evaluation_baseline.md:3`、`docs/evidence.md:3575`。
- [已验证] 历史局部评测记录存在；2026-10-27 四例知识对照记载三个 completed、一个 partial，四份原评分 `success_count=1`、`hard_gate_status=passed`；依据 `docs/evidence.md:3548`。不能将该四例替代完整开发集或独立留出。
- [未验证] 本次未打开原始评分产物、数据库备份、旧 Gold 或独立留出，未核验历史数字的底层原始数据。没有当前 HEAD 的统一质量/延迟/费用数字。

## G. 规则与文档负担

| 范围 | 数量/行数 | 证据 |
|---|---:|---|
| 仓库 AGENTS.md | 1 / 89 | [已验证] S2；不计本会话额外传入的导师规则及用户全局规则。 |
| docs/plans Markdown，含 history | 4 / 2542 | [已验证] S2。 |
| improvement_and_learning_plan.md | 1 / 299 | [已验证] S2。 |
| single_node_production_style_ai_application_roadmap.md | 1 / 1457 | [已验证] S2。 |
| agent_architecture_refactor_requirements.md | 1 / 663 | [已验证] S2。 |
| history/agent_core_first_execution_plan.md | 1 / 123 | [已验证] S2。 |
| docs 全部 Markdown（创建报告前） | 15 / 10022 | [已验证] S2；不含 JSON、仓库外文档或本报告。 |
| 唯一 evidence 台账 | 1 / 3577 | [已验证] S1；本次只读，未追加。 |

- [已验证] 新会话固定规则最少涉及 3 个文件：`AGENTS.md`、improvement 计划、主路线图，共 1845 行；依据 `AGENTS.md:5`、`:11`。此外明确要求当前源码、测试和工作区差异，但没有固定文件数量。
- [已验证] 若再遵循 `docs/README.md:3` 的阅读导航，去重后是 6 个固定文档：上述三个，加 `docs/README.md`（45 行）、模块结构（106 行）、evidence（3577 行），共 5573 行；依赖的源码/测试另算。
- [推测] “开会话必须先读多少文件”不能给出包含源码在内的单一固定数；具体变更涉及几层，阅读范围就会变化。路线图旧入口冲突会进一步增加解释负担，证据见 D6。

## H. 运行环境

| 环节 | 源码/文档要求 | 本次实际具备 |
|---|---|---|
| Python 工具链 | [已验证] `backend/pyproject.toml:9` 要求 Python >=3.10,<3.15；README 使用根目录 `.venv`。 | [已验证] E2：系统 Python 3.10.8；根目录 `.venv/Scripts/python.exe` 不存在；Ruff 0.15.22。 |
| Node 工具链 | [已验证] `README.md:73`–`:76` 列开发前置；`frontend/package.json:10` 提供测试。 | [已验证] E2/T3：Node v24.16.0、npm 11.13.0、node_modules 存在，测试能启动。 |
| Docker | [已验证] `docker-compose.yml:31` 等定义本机服务。 | [已验证] E1：Docker CLI 能访问 daemon，部分容器 Up；不代表整体应用可运行。 |
| 平台 PostgreSQL/pgvector | [已验证] `docker-compose.yml:31`–`:32` 定义平台 PG；保存任务、文档、审计。 | [已验证] E1：`agent-platform-postgres` 为 Exited (127)；另有 `ri27-pg` Up，仅显示容器内 5432，归属与是否可用于本项目未验证。 |
| Redis | [已验证] `docker-compose.yml:90`–`:91`；任务 broker 由 Outbox 投递链使用。 | [已验证] E1：`agent-platform-redis` Exited (137)。 |
| API/Worker/Beat | [已验证] `docker-compose.yml:173`、`:197`、`:245`、`:323` 定义相关服务。 | [已验证] E1：API Restarting (3)，分析 Worker、report-worker、Beat Up；实际消费/调度能力未验证。 |
| 经营库 | [已验证] `docker-compose.yml:353`、`:370`、`:386`；会话要求数据源与 Schema 快照，`conversations/service.py:217`–`:232`。 | [已验证] E1：平台经营库及 acme/beta 演示经营库均 Exited (255)；库内容和只读角色未验证。 |
| 模型与检索 | [已验证] `core/settings.py:93`–`:114` 配置 Provider/模型/重排/传输；`knowledge/tool.py:86` 使用本地嵌入。 | [未验证] 有效配置、供应商可用性、价格表、模型缓存及下载完整性未检查，不发起模型请求。 |
| 文档及公司数据 | [已验证] `conversations/service.py:179`–`:188` 选当前公司可见的已处理文档；`:219` 要求数据源。 | [未验证] 没有登录、读取现有租户业务数据或创建账号；有效文档、成员权限、快照内容未知。 |
| 容量信号/对象存储/扫描 | [已验证] Compose 定义 `capacity-signal/localstack/clamd`，位置 `:69`、`:131`、`:118`。 | [已验证] E1 显示三者 Up/healthy；[未验证] 未做应用侧连通性或授权验证。上传入口当前冻结，不等于这些依赖的所有功能已被检验。 |
| 前端服务 | [已验证] `docker-compose.yml:229` 定义前端；`frontend/vite.config.ts:9` 默认代理本机 API。 | [已验证] E1：`agent-frontend-1` Exited (255)；T3 只证明测试进程可执行。 |

- [未验证] 完整运行还需要平台应用/迁移角色、Redis 连接、经营只读连接、Provider、价格/预算配置、公司成员、数据源快照、所需知识语料；实际敏感值均未检查，凭据统一记作 `***`。字段声明依据 `backend/app/core/settings.py:18`，任务前置依据 `conversations/service.py:160`。
- [未验证] 文档中的候选启动命令为根目录 `docker compose up -d --build`、`docker compose ps`；本地方式另需迁移、Uvicorn、Celery 及前端进程。此次没有运行这些命令，也没有运行可能加载 `.env` 的 `docker compose config`，不得把 README 步骤视为本次复现证明。

## I. 我认为最卡的三个问题

1. [推测] **先恢复可检查的依赖环境，再讨论业务链。** 本次 E1 已显示平台 PG/Redis 退出与 API 重启，README 指定解释器又不存在；接手者当前无法直接复制验证命令得到同口径结果。[已验证] 依据 E1、E2、T1；本次遵守只读限制，没有恢复服务。
2. [推测] **缺少同一版本的统一评测依据。** 历史记录混合不同版本，仍有一个数据案例失败及两个混合案例未执行；即使局部修正有对照，也不足以判断当前 HEAD 的整体行为。[已验证] 依据 `docs/evidence.md:3574`–`:3575`；一个旁录版本在本地不可解析，见 D7。
3. [推测] **接手者需要先理清执行规则与证据层次。** 三份固定规则材料就有 1845 行，路线图仍指向历史计划；同时需区分源码分支存在、历史评分和本次实际测试结果。[已验证] 数量依据 S2/G，入口冲突见 D6；本报告因此不把历史数字换写成当前能力结论。

## J. 无法确认的事项与未执行步骤

- [未验证] 后端非 e2e/slow pytest：没有运行，原因是缺少 README 解释器、主依赖退出、测试启动会读取 `.env` 并产生文件/迁移副作用；失败测试名和数量未知。
- [未验证] 项目声明的 Ruff 0.16.1：没有安装或执行；仅有本机 0.15.22 的八条诊断，不能证明 CI 状态。
- [未验证] 当前 API 重启根因、进程实际代码版本、后台 Worker 是否存在连接重试或未消费任务：未读取运行日志和凭据，未进入容器调试。
- [未验证] 当前 HTTP→Outbox→Worker→SQL/RAG→发布端到端执行：没有提交问题，依赖不足且该操作会写库/可能发生模型费用。
- [未验证] 全量开发评测、两个混合路线、独立留出、oracle 审核、统一阈值、费用/延迟比较：未运行；本次仅引用带日期文档。
- [未验证] 真实跨公司隔离、RLS、发布前撤权、租约过期、重复消费、取消、恢复及审批竞态：本次没有故障注入或真实数据库验证；源码存在检查不代表所有时序已被证明。
- [未验证] 报告保存后的记忆/assistant 消息第二次提交失败时的展示一致性：源码存在两次 commit（`lifecycle/execution.py:656`、`tasks.py:465`），但本次没有构造故障，不列为已复现缺陷。
- [未验证] 原始 artifacts、数据库 dump、历史版本映射和旧评测产物的完整性：仅检查未跟踪目录状态，不打开可能包含业务内容或敏感数据的原始产物。
- [未验证] 前端 build、浏览器 UI 联调、依赖漏洞、全局类型检查、备份恢复、负载、长期运行、模型质量、用户独立学习能力：不在此次实际执行范围内。
- [已验证] 一次前端路径读取误在 backend 工作目录执行而失败，随后在仓库根目录读取成功；PowerShell 不展开传给 rg 的路径 glob，随后改用目录加 `-g` 读取。本次未对业务测试反复重试；此前大段文档输出有截断，报告所用关键段落另以行号定向读取。

## K. 建议接手者优先阅读的十个文件

- [推测] 以下顺序先确定规则和证据，再沿任务创建到发布追踪；是阅读建议，不代表读完即可操作现有数据库。

| 顺序 | 文件 | 为什么先读/证据 |
|---|---|---|
| 1 | `AGENTS.md` | [已验证] `:3`–`:11` 定义当前顺序、冻结范围、预读要求；先避免沿旧计划推进。 |
| 2 | `docs/plans/improvement_and_learning_plan.md` | [已验证] `:21` 给设计模板，`:213` 给阶段顺序，`:234` 给教学分工。 |
| 3 | `docs/plans/single_node_production_style_ai_application_roadmap.md` | [已验证] `:14` 起列边界与门禁；结合 AGENTS 处理 `:5` 的历史入口，不把目标当现状。 |
| 4 | `README.md` | [已验证] `:68` 为环境启动说明，`:142` 为验证命令；需结合此次解释器与依赖缺口。 |
| 5 | `docs/evidence.md` | [已验证] 先看 `:3571` 的 2026-10-27 汇总，再回溯失败和修正；历史数字不得直接复用为当前结果。 |
| 6 | `docs/design/evaluation_baseline.md` | [已验证] `:3` 标记未冻结，`:9`–`:13` 解释 fixture、Observation 与盲测边界。 |
| 7 | `backend/app/modules/conversations/service.py` | [已验证] `:160` 是权限范围、数据源、用户消息、任务和 Outbox 的事务汇合点。 |
| 8 | `backend/app/modules/workflow/tasks.py` | [已验证] `:511` 进入 Worker，`:640` 调图，`:354` 保存结果；可从这里追到运行时和发布边界。 |
| 9 | `backend/app/modules/workflow/orchestration/graph.py` | [已验证] `:93` 定义节点/条件边，`:173` 构造状态并恢复；用于核对实际路线而非只读架构示意图。 |
| 10 | `backend/app/modules/workflow/lifecycle/execution.py` | [已验证] `:256` 原子认领，`:566` 终态写入及执行权条件；随后按调用点查 Runtime 和报告校验。 |
