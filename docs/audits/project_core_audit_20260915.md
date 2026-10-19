# 当前项目审计：Agent 底座与五项核心工程能力

> 本文主体为先前快照，不代表最新候选。当前复查见 [新执行计划现状](../plans/history/agent_core_first_execution_plan.md#1-实查现状)：507项收集；modules 433通过、1失败、3跳过；Observation候选已存在，空范围修复已进入工作区；真实业务全链未验证。原M1-IN独立里程碑已取消，以下历史阶段说明不再决定执行顺序。

> 整体范围最终澄清：各模块生产级改造与评估、追踪、权限、回滚、成本是同一个目标。以主路线图第 0.4 节全项目矩阵联合验收；阶段只决定先后，不允许部分收口。

日期：2026-09-15。范围：当前源码、测试、工作区差异、主路线图、设计账本及本机只读状态检查。

> 用户澄清后的范围：全部现有及主线模块向生产级设计与实现演进；五核心贯穿各模块。上下文和记忆的完整目标见主路线图第 0.3 节，不能将长期记忆治理降为可选项。

## 1. 总判断

现有架构适合继续改造成“单节点验证、未上线的生产级 Agent”，不需要换框架或推倒重来。当前是有执行与治理骨架、部分模块有测试证据，但真实业务评估—追踪—权限—回滚—成本尚未统一验收的阶段。不能给一个没有分母的完成百分比。

旧计划的主要问题：环境状态过时；完整多模态排在权限止血前；评测、成本、回滚虽写成横向能力，实际工作包过晚；新增功能与现有模块工程改造没有明确区分；上传/附件摄取只停留在矩阵与设计包，未作为可验收实施链；整体 Ready 条件容易阻塞修复测量工具本身。路线图现调整为 M0 -> M1-IN -> M1–M5，上传模块是主线中的独立交付阶段，不是额外启动第二条主线。

“生产级设计”要求明确不变量、失败行为、资源预算、恢复方式及验证证据。单机足以验证这些机制，但不能证明高可用、企业流量或长期线上可靠性。

## 2. 本轮验证与证据边界

- HEAD：`a0d8578`，`Remove obsolete code and simplify project structure`。仅作为代码参照，不称已验证业务基线。
- 工作区已有附件解析/OCR/版本绑定/引用等修改与未跟踪代码、迁移和测试，另有简历文件；均保留，未提交或合并为基线。本轮仅调整项目文档。
- 在 backend 目录运行 `../.venv-py313/Scripts/python.exe -m pytest tests/unit -q --disable-warnings --maxfail=2`：**427 passed, 3 skipped, 1 warning，11.91s，退出码 0**。
- 测试收集 `../.venv-py313/Scripts/python.exe -m pytest tests --collect-only -q`：**499 tests collected，退出码 0**。收集不等于执行。
- 上述模块测试含 FakeDb、模型替身等；未运行全量集成、真实业务 Worker E2E、迁移/恢复/回滚演练，未产生当前冻结业务质量基线。
- `docker compose ps` 显示 API、Worker、Beat、PostgreSQL、Redis、ClamAV 在运行；数据库/Redis/扫描服务显示 healthy。运行状态不能证明容器镜像与当前未提交代码一致，也不能证明业务链路完整。
- 本机：16 逻辑处理器，约 15.8 GiB RAM。未测本次负载峰值、吞吐或存储服务能力。
- 最小只读反例运行确认：空 `allowed_chunk_ids` 的 Case 接受返回 chunk；数值与确定性校验失败的 Case 仍可获得汇总 `hard_gate_passed=True`；RAG 首条 4000 字符证据在 `max_chars=3000` 时完整进入 Prompt。这些行为未在本轮修复。
- 历史审计目录存在，不等于其产物适用于当前 HEAD/候选。历史文档 `backend_product_delivery_plan.md`、`multi_agent_workflow_decision_flow.md` 已不存在，遵循当前 AGENTS 与主路线图。

## 3. 五核心当前进度

| 能力 | 当前已有 | 当前关键缺口 | 判定 |
|---|---|---|---|
| 评估 | EvaluationCase/Observation、确定性 evaluator、CLI 和 fixture | CLI 接收外部 Observation；未找到实际持久化任务到业务 Observation 的自动适配闭环；空白名单与汇总硬门禁有反例；substring 不能证明语义 | 测量雏形，先修测量契约再谈优化收益 |
| 追踪 | request_id、attempt、WorkflowEvent、ToolCallRecord、ModelCallRecord、公司指标聚合 | 完整输入/Prompt/资源版本、授权决定、证据与发布关联未统一证明；普通 SQL 日志仍有正文 | 有基础审计，未验收完整 trace |
| 权限 | 公司成员、冻结文档 ID、SQL 表范围、公司向量过滤、RLS相关测试、只读经营库 | 空范围在 Worker 变 None；ToolRuntime 对 None 跳过子集检查；动态撤权与文档版本不完整；候选附件最终发布范围参数未接通 | 架构方向正确，有优先阻断项 |
| 回滚 | Git、租约/Checkpoint、执行权条件、备份/恢复脚本 | Checkpoint 未按版本兼容筛选；Outbox published 不等于认领；恢复脚本只校验表数；没有本轮三类回退/恢复证据 | 有部件，未形成演练闭环 |
| 成本 | 任务级模型/工具预算、调用预留、usage、Fallback轨迹、聚合 | DeepSeek 费用默认 0；OpenAI 固定价格未按模型/版本选择；没有最大输出费用预留；usage 丢失可能归零；真实并发/崩溃结算未证明 | 已实现基础治理，尚不能声称严格费用控制 |

### 上传与附件摄取的当前判定

候选工作区已经有三个入口层（普通 multipart 上传、直传会话创建、直传完成确认）、quarantine 对象存储接口、扫描/解析 Celery Job、处理 Outbox、不可变 `InputArtifactVersion`、任务冻结版本和受限附件上下文。它说明设计方向可继续，不说明模块已经完成：本轮没有运行真实对象存储 + ClamD + Celery 的从上传到最终引用闭环；附件引用范围也尚未接通最终正常/审批发布调用。解析器当前主要按文件后缀路由，计划要求的 extension/MIME/magic 三者一致性和完整隔离资源证明仍须以源码与真实反例补齐。

因此，上传模块的正确状态是“已有候选部件，未通过 M1-IN 验收”，不能写成已完成或仅剩 UI。M1-IN 的唯一入口在主路线图第 16 节；其中的状态、授权、恢复、追踪与成本验收同样适用五项治理，不等到后续阶段才补。

### 优先问题的连续调用链

1. `create_conversation_task_service` 冻结 `document_ids` -> `process_analysis_task` 仅在列表非空时传入 `run_analysis` -> 默认 None -> `RAGTool` / `retrieve_evidences` -> `search_similar_chunks` 省略文档过滤。与此同时 `_frozen_allowed_chunk_ids` 对空列表返回 None -> `validate_report` 跳过 chunk 子集检查。公司过滤仍存在；这里不能把“任务范围扩大”直接夸成已实测跨公司泄露。
2. 候选 `validate_report` 增加 `allowed_attachment_citation_ids` -> Worker 正常发布和审批发布调用只传 `allowed_chunk_ids`。因此不能凭附件校验器单测通过，宣称最终发布已接通附件范围保护。
3. Gateway -> `reserve_model_call` 预留调用次数和输入估计 -> 模型调用 -> `record_model_call` 累加 Token/费用。预留不包含最大输出成本；DeepSeek 成功记录未传费用；当前账本不能支撑可信财务比较。修复需统一入口，不是只改聚合展示。

## 4. Agent 基础设计逐项判断

### 4.1 架构与模块：保留模块化单体，局部重构契约

依据：`workflow/graph.py` 已用 LangGraph 串联 Planner、Data、Knowledge、Reviewer 和确定性 Router；`workflow/execution.py` 管认领、租约、Checkpoint 和终态；平台库负责权威状态。这种受控工作流适合只读经营分析。

改法：API/Application 管身份与创建事务；Workflow 管路线；Runtime 管授权、执行权、预算和调用；Data/Knowledge 返回证据；Reporting 管草稿与确定性发布；Evaluation 只读取结果评估，不掌握生产发布权。保持当前目录为主，不因逻辑边界而拆微服务。

`WorkflowState` 的大量 dict、ORM 对象、回调与运行时对象混合只适合执行期；当前 `_checkpoint` 已选择白名单快照，不能误称所有对象都被持久化。补一个版本化持久化 DTO，与执行期 context 分开；边界使用现有 Pydantic 结构，不给每个函数建抽象类。`task_spec.py` 当前只有 id，不能当作不可变任务契约已完成。

验收：节点输入/输出契约、非法路由/恢复节点、Checkpoint兼容、终态一致性、取消和迟到结果。M1/M2 完成。

### 4.2 Planner / Data / Knowledge / Reviewer：职责保留，收紧决定权

- Planner：已有 analyze/direct_response/scope_exit/needs_clarification/refuse 等结构化分支和语义复核。保留；补关键时间/实体/指标来源和冻结运行版本。语义复核是候选意见，不能批准权限。复核调用的质量收益和费用需做消融比较，不凭“多一个 Reviewer”认定更可靠。
- Data：保留候选 SQL 与受控执行、有限修复；模型负责提出候选，代码负责 QueryContract、只读与数值。统一内部 repair 与外部 replan/attempt 的总预算，不允许每层各自有界但总量失控。
- Knowledge：返回版本化、授权、限量证据及缺口；若已有 RAG 回答和最终 Composer 重复生成，先测是否能只传 EvidenceBundle 减少一次生成，不能未测就删除必要语义判断。
- Reviewer/Composer：可提出支持关系、冲突、草稿；确定性代码验证数字/引用/范围/状态并唯一发布。保留语义判断和确定性门禁的区别，不声称代码能完全证明自然语言因果正确。

验收：每个节点有失败/不足/拒绝输出，所有循环有总步数与费用上限，重试只重跑必要节点；错误路线与证据不支持的回答进入 Bad Case。M1–M3 完成。

### 4.3 上下文：已有有界方案，但需要统一 Token 预算

依据：`build_conversation_context` 按最近消息选择、单条与总字符限制并记录截断；Planner 接收冻结 context、记忆和反馈。`knowledge/rag/engine.py::build_prompt` 首条证据即使超过上限仍保留。

改法：建立统一 Context Builder 契约，输出片段来源、版本、角色/可信度、Token 用量和舍弃原因；优先保留系统规则、当前问题、冻结范围，再装相关历史/证据。为模型最大输出预留空间，最后在 Gateway 对实际完整输入再次检查硬上限。保留字符上限作为廉价前置保护，但不能把字符当 Token。长文本分块或拒绝，截断不得留下失真的数字/引用。

不需要先增加复杂摘要 Agent。短历史、长历史、指代、旧时间、冲突信息和恶意历史使用同一组 Case 比较。上下文大小是 M1/M2 必做，不属于可无限推迟的长期记忆扩展。

### 4.4 记忆：已有基础，工作/会话/长期记忆均须完成治理改造

依据：`memory/service.py::planner_memories` 检查成员 approved、company/user、revoked/expiry，限 8 条；写入只保存报告 confirmed_facts 与 limitations，有来源与幂等键。并非完全没有记忆治理。

缺口：8 条不等于 Token 有界；写入没有默认 expires_at；读取没有逐条验证原始证据当前权限、版本和任务相关性；已有报告“校验通过”也不代表事实计算已经足够强。

改法：区分工作状态（本次执行）、会话上下文（理解省略）、长期记忆（历史线索）。当前数值和归因必须重新取证，历史记忆不能直接升格为当前证据。长期记忆补来源资源版本、失效/删除传播、时效、冲突与选择 manifest；未补齐时关闭其 Planner 注入或仅限无敏感业务内容的偏好，历史记录保留。先对比无记忆与有记忆质量/成本，不能先上额外记忆框架。

验收：成员撤权、来源文档撤回、记忆过期/冲突、任务跨公司/跨用户、注入、超长内容、历史数字冒充当前数字。M1 实现契约和来源隔离，M3 评测实际价值，M4 验证失效/删除/恢复传播；临时禁用不是最终完成方案。

### 4.5 工具：保留 ToolRuntime，必须成为不可绕过边界

依据：现有 `ToolInput.parameters` 是任意 dict，`ToolOutput.data` 是 Any；Runtime 有白名单、任务预算和元数据审计；Agent 可以使用注入工具，构造器也存在直接工具默认值。

改法：每个已用工具明确输入/输出 Schema、版本、结果大小、timeout、错误分类；授权字段不进入模型可填写参数，服务端注入 AuthorizedExecutionContext。生产节点只能拿到 Runtime 包装工具；测试替身明确隔离，不能因构造器默认值而旁路授权。SQL 结果和 RAG 证据分别用已有结构强化，无需通用插件平台。

验收：伪造/缺失公司范围、空文档范围、未知工具、坏参数、畸形/过大返回、超时、预算耗尽、旧 attempt；本地工具和未来 MCP 工具必须通过同一组契约。M0–M2。

### 4.6 MCP：适合扩展接入，不是当前生产化前置条件

当前 backend/app 搜索未发现运行时 MCP 接入实现。不要把开发环境能调用 MCP 工具当作业务 Agent 已接入 MCP。

MCP 是工具发现/调用与结构描述协议，不替代应用授权、预算、结果验证和审计。官方协议要求工具输入校验、访问控制，并明确工具 annotations 的信任边界。[MCP 工具规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

目前 SQL/RAG 都在同一后端，内部调用最合适。出现真实外部系统接入或多客户端共享需求时，先接一个只读 MCP 工具：固定服务器与工具 allowlist、版本/Schema 指纹、最小凭据、超时、结果上限、费用与 trace；工具列表变化不能自动获得权限。不把任意服务器地址、系统 shell 或本机全盘暴露给模型。

若目标包含 MCP 工程学习，可在 M3 后做独立小切片，用相同业务 Case 比较内部调用与 MCP Adapter；其失败不得绕开 Runtime。无需为简历把全部内部函数包装为网络服务。

### 4.7 Skill：可作为版本化业务流程包，不能代替代码门禁

Skill 是可复用的指令、资源及可选脚本包；Tool 是实际执行动作的接口，两者职责不同。[Agent Skills 官方概览](https://agentskills.io/home)

当前业务运行时未见独立 Skill 加载/治理实现；现有 Prompt 与业务配置不自动等同标准 Skill 体系。开发用 SKILL.md 与产品运行时 Skill 也不是同一层。

单一经营分析主线先保留版本化 Prompt/指标配置；出现两个以上真实不同分析流程或明确复用需求，再拆如“销售变化分析”流程包。最小清单可含 skill_id/version、适用条件、输入输出契约、引用 Prompt/指标版本和所需工具。服务端策略与工具权限取交集，Skill 不能授予自己新权限。仅装可信包、记录内容 hash、按需加载，不允许运行用户上传脚本。

验收：选错 Skill、版本回退、缺工具、超预算和恶意指令不能改变权限/发布门禁。它可提升复用性，不作为当前核心完工条件。

### 4.8 RAG：保留 pgvector 与重排，优先证据/权限改造

依据：向量候选检索后有字符重叠混合评分和重排模块；按 company 与 document_ids 查询；证据有页/段落信息；充足性使用条数与平均相关分。这些可做检索启发式，不能证明支持业务结论。

改法：不可变 document/chunk 版本与内容 hash -> 当前 ACL + 冻结范围前置过滤 -> 限量召回/重排 -> 统一上下文预算 -> EvidenceBundle（稳定引用、来源、时效、冲突、缺口）-> 逐条 Claim 支持判断 -> 发布。先修空范围，不换向量库；先以困难样本决定切块/混合召回/重排参数，每次只改一个变量。原始召回指标和最终回答指标分开。

验收：越权/撤回/重新摄取/版本切换/注入/无匹配/证据冲突；Recall@k/MRR 等检索指标，加人工校准的支持正确率、无依据声明率、答案质量与成本。M1/M3；嵌入/重排版本回退纳入 M4。

### 4.9 SQL：保留受控自由 SQL，校验与计算需明显加强

依据：`sql_validator.py` 当前强制单 SELECT 与表范围，明确允许 wildcard/flexible joins；`sql_executor.py::_apply_row_limit` 只要 SQL 字符串含 LIMIT 就不加上限，连接无显式 connect_timeout；`query_contract.py` 已有列/结果类型等结构，`query_validation.py` 主要查列和行形状；`facts.py` 主要把前 5 行渲染成事实句。

改法：自然语言 -> 结构化意图/时间口径 -> 版本化指标与 QueryContract -> SQL 候选 -> AST 只读、范围、列/关联/函数/复杂度和硬 LIMIT -> 独立只读库 -> typed result -> Decimal 计算 -> 数值/公式/来源证据。模型不能以自填 expected_columns 自证业务正确；关键口径与公式由服务端指标定义和 Gold 约束。补连接/语句/任务三层时间边界与结果字节上限，SQL 普通日志改为 hash/结构元数据。

不把所有 Join 禁掉，也不改成固定查询-only；围绕被支持业务定义必要规则。测试不同数据分布下的结果等价性，覆盖重复 Join、漏状态过滤、错误日期列、空值、零分母、单位/币种、超大 LIMIT 及写入拒绝；SQL 可执行不算业务正确。M1 权限、M2 资源限制、M3 业务正确性。

## 5. 当前适合的目标架构

```text
API / Application（身份、幂等、冻结输入）
  -> PostgreSQL Task + Outbox
  -> Worker（认领、当前授权、租约、Deadline）
  -> Context Builder（来源与 Token 预算）
  -> Planner -> Data / Knowledge -> Reviewer / Composer
                  |          |
                  +-- ToolRuntime -- 本地 SQL / RAG / 可选 MCP Adapter
  -> 确定性 Publish Gate -> 报告、消息、事件事务

横贯执行：版本、授权、trace、任务级调用/费用账本
执行之后：持久化 Observation -> 评测/Bad Case -> 候选采用或回滚
记忆：只提供受控历史线索；当前事实重新取证
Skill（条件启用）：版本化流程配置；不持有权限或发布权
```

trace 的事件关联采用清晰父子/调用关系，复用现有持久化记录；可参照 [OpenTelemetry 追踪模型](https://opentelemetry.io/docs/concepts/signals/traces/)，不要求立即部署 Collector 和多个观测产品。备份/恢复使用现有 PostgreSQL 工具，按 [官方备份说明](https://www.postgresql.org/docs/17/backup-dump.html) 选择明确方式，并补应用与对象一致性验证。

## 6. 修改与下一步

主路线图已改为：M0 测量契约与权限阻断 -> M1 权限/版本/上下文/追踪 -> M2 成本/工具/故障控制 -> M3 SQL/RAG/业务评测 -> M4 回退/恢复演练 -> M5 本机完整验收。设计账本同步声明条件能力边界。

第一个用户实现切片：给评测器空白名单和硬门禁写失败测试，修复后通过；解释为什么“未知/没有事故记录”不能当作通过。再接一个真实持久化字段到 Observation。模型负责审查、解释与机械工作，不包办所有核心代码。

本轮结论是“已完成分析与计划修订”，不是“上述生产代码缺口已修复”。后续每个切片记录工程结果和用户独立完成的证据。

## 7. 再审结论与修订（2026-09-15）

原计划模块覆盖较完整，但不能通过严格的生产级实施审查：授权竞态、审计故障、预算崩溃对账与取消后费用、删除后恢复、供应链/数据外发/输出处理缺少具体门禁；部分已确认目标未落阶段，SLO/RTO/RPO 缺少冻结时间。

主路线图第 0.5 节已补强这些要求；设计账本过时的 InputArtifact 状态已纠正，全局目标同步为生产级设计与工程要求。该轮验证仅包含文档一致性、关键门禁覆盖和差异检查，未重新运行业务测试或生产级演练。前文 427/499 是当日先前执行证据，不是本次计划修订带来的新验证。

结论：修订后的计划可作为全项目生产级改造的实施依据；每个模块仍需在自身实现前完成契约与具体阈值，随后通过真实验证。计划完整不等于实现合格，更不能保证未上线的系统已有线上成熟度。
