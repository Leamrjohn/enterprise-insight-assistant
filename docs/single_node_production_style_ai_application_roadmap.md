# 企业经营洞察助手：无限接近生产级的系统设计与演进路线图

> 本文档是项目唯一主路线图，也是架构约束、阶段顺序和验收证据的最高项目规则。
> 目标是在单节点可验证环境中，建设一个可测量、可比较、可恢复、可解释、可审计的企业经营分析 AI 应用。
> 重心是业务建模、契约、权限、证据、状态、恢复、评测与演进；部署只作为最后的验证载体。

---

## 0. 计划审计结论与使用规则

本路线图已经按“用户输入 + 19 个纵向处理环节 + 横向生产能力 + 当前源码/测试/差异”重新核对。审计中修正了以下会造成返工或错误安全结论的问题：

1. 原阶段顺序与 Work Package 顺序冲突，现统一以第 16 节和 18.1 的同一依赖图执行；
2. task status、工作流 stage、分析结果和报告发布状态原本混用，现拆成四套互斥语义；
3. 评测原本放在后期，现由 P0-0 先建立可运行基线和 smoke，P0-H 再完成真实业务晋升体系；
4. TaskSpec 原先依赖尚不存在的文档版本，现先做 InputArtifact/DocumentVersion/ChunkVersion，再冻结任务资源；
5. 空文档范围、Outbox 审批事件、公开 Retry、幂等和旧任务迁移原本存在含糊或实际风险，现拆成独立契约与验收；
6. 文本/文件/图片、意图/参数、上下文/记忆、路由/规划、工具、结果验证、HITL、持久化、观测和评测已逐项映射到第 5.1 节，不再只是泛化名词；
7. 安全、权限、稳定性、性能、成本、持久化、版本化、测试和运维已映射到阶段与工作包，不留到开发末期补做。

计划通过不等于可以立即修改生产代码。当前只有“路线图设计”可进入确认，实施仍被 P0-0 阻塞：测试环境无法收集、巨大 dirty tree 尚未分类、真实主链 baseline Observation 尚未建立。

允许删除或重构旧设计、契约和兼容层，但每次必须同时写出受保护不变量、失败行为、数据/API 迁移、验证证据、回滚路径和未证明边界。缺任一项不得以“更生产级”为名开始重写。

---

## 1. 目标边界：生产级不等于部署复杂

本项目追求的“无限接近生产级”，不是堆更多 Agent、框架、微服务和部署组件，而是让系统具备以下性质：

1. **行为可预测**：相同输入、数据快照、权限和版本，应产生可解释的等价业务结果。
2. **权限不可绕过**：模型、Prompt、用户输入和历史上下文都不能扩大服务器确定的公司、数据源、表、字段和文档范围。
3. **数字可重算**：确定性数字、公式、单位、时间口径和来源可以由代码复算。
4. **声明有证据**：事实、假设、建议和限制使用不同契约；引用存在不等于引用支持声明。
5. **失败可恢复**：重复投递、Worker 崩溃、超时、取消、撤权和旧执行回写不会破坏最终状态。
6. **决策可审计**：能够回答谁在何时基于哪个快照、版本、工具和证据生成结果。
7. **质量可比较**：任何优化都必须与冻结基线、冻结留出集和成本/延迟一起比较。
8. **系统可演进**：工作流、Prompt、模型、工具、指标、Schema 和评测集都有版本与兼容边界。

最低部署要求只有：干净环境可启动、迁移可执行、真实依赖 E2E 可复现、备份恢复可验证。Kubernetes、多区域、高可用集群和复杂编排不是当前主线。

### 1.1 完成后可以与不可以宣称什么

证据充分时可以宣称：

- 具备生产风格的单节点系统设计；
- 具备严格权限、证据、状态恢复、评测和审计闭环；
- 适合受控内测、低并发试运行或作为进一步生产化的可靠基线。

不能仅凭本路线图宣称：

- 多节点高可用、跨区域容灾或明确 SLA；
- 已承受真实企业规模流量；
- 任意业务问题都能正确回答；
- 测试通过等于真实业务 E2E；
- RAG Recall 提升等于最终报告质量提升。

---

## 2. 当前代码复核结论（2026-09-08）

本节只记录当前代码事实，不把目标设计写成已实现能力。

### 2.1 已有且必须保留的骨架

~~~text
API / Conversation
  -> 同事务创建消息、AnalysisTask、冻结范围、Outbox、占位回复
  -> Outbox 发布 Celery 消息
  -> Worker 原子认领 execution_id
  -> Planner
  -> Data Agent / Knowledge Agent
  -> Reviewer / Composer
  -> 确定性校验
  -> 所有权保护下持久化结果
~~~

当前实现还包括公司成员身份与范围、独立只读经营库配置、Schema Snapshot、SQL 单条 SELECT 与表范围检查、ToolRuntime 白名单和预算、租约/执行尝试/Checkpoint/过期恢复、受控工作流与有限重试、结构化报告、基础数字和引用校验、业务评测数据结构以及模型/工具调用记录。

这些是正确的骨架，不等于生产级已经完成。

### 2.2 当前最重要的设计缺口

| 优先级 | 当前代码证据 | 风险 | 目标修复 |
|---|---|---|---|
| P0 | SQL Validator 只强制物理表范围，并明确允许通配符和灵活 Join | 可能读取不必要字段，错误 Join 仍可生成错误结论 | 列、Join、函数、复杂度、结果形状和语义校验 |
| P0 | 指标定义主要是 Prompt 文本 | LLM 可使用错误公式或漏掉强制过滤 | 版本化 MetricDefinition，代码选择、验证、计算 |
| P0 | Fact Builder 只是把最多 5 行渲染成句子 | 缺类型、单位、公式、口径、血缘和空值语义 | typed calculation 与可复算事实模型 |
| P0 | 最终校验主要验证 Schema、引用范围和数字是否出现过 | 不能证明数字关系、归因或引用语义正确 | Claim–Evidence Graph 与完整发布门禁 |
| P0 | Outbox 只有 pending -> published | 已发送但认领前丢失会导致任务永久 queued | 已发布未认领对账和安全重投 |
| P0 | 租约主要在节点/Checkpoint 边界续期 | 长模型/SQL/检索调用可被重复认领和计费 | 独立心跳、节点 Deadline、总 Deadline、fencing |
| P0 | 恢复 Checkpoint 未按工作流版本筛选 | 新代码可能载入不兼容旧状态 | 兼容指纹、迁移器或安全重启 |
| P0 | 任务创建时冻结权限，长任务缺系统化撤权复核 | 成员禁用或文档撤回后仍可能访问/发布 | 冻结范围 + 当前权限否决 |
| P0 | `document_ids=None` 表示创建时全选，但冻结后的空列表在 Worker/RAG/报告校验中又可能被解释为“不限制” | 无文档权限或显式空范围可能扩大成公司全量文档范围 | 用显式 `ALL_AT_CREATION / EXPLICIT / EMPTY` 范围代数；执行期只接受解析后的不可变版本 ID，`EMPTY` 永远 deny-all |
| P0 | 文档更新会原地修改记录并重建 chunk，任务只冻结 document id | 旧任务和报告无法重放当时内容，引用身份随重摄取漂移 | 先建立不可变 DocumentVersion/ChunkVersion，再允许 TaskSpec 声称冻结文档版本 |
| P0 | Outbox 对 `task_id` 唯一，而审核批准会给同一任务再次创建 `analysis_task.created` 事件 | 真实会话任务审批时可能唯一键冲突，创建事件与发布语义混淆 | 审批在同事务校验并发布草稿，不重跑分析；通用 Outbox 改为事件 UUID + event_type + generation，按真实外部副作用使用 |
| P0 | `request_id` 只有索引，没有唯一作用域和 payload hash | 网络重放可能创建重复消息、任务和费用；同 key 异 payload 无稳定冲突 | 数据库唯一幂等键、canonical payload hash、原响应重放 |
| P0 | task status、工作流 stage、分析结果、报告状态使用重叠枚举 | 证据不足、技术失败、取消和成功发布容易被错误迁移或错误展示 | 拆分 ExecutionStatus、ExecutionStage、AnalysisOutcome、PublishStatus，并建立唯一投影表 |
| P1 | 业务评测只有 5 个开发 Case + 1 个留出 Case，运行器不调用 Agent | 无法证明真实链路或稳定质量 | 真实 Worker Observation Adapter、人工 Gold、扩大冻结集 |
| P1 | Prompt 版本不总能落为具体值 | 无法精确复现模型行为 | 统一运行版本指纹 |
| P1 | 未挂载旧 /tasks 实现与新主链并存 | 未来可能形成非事务旁路 | 删除、封存或适配到唯一主链 |
| P1 | 工具日志可能包含原始 SQL | 敏感字面量可能进入普通日志 | 默认保存 hash、模板和结构化元数据 |
| P1 | SQL 行数上限、列/Join/类型/粒度和连接 Deadline 尚未形成闭环 | 已有大 LIMIT 可绕过 max_rows，慢连接或语义错误查询仍可能拖垮执行或产生错误事实 | AST 重写硬上限、连接/语句 Deadline、结果契约和 typed calculation |

### 2.3 当前证据边界

- 工作区存在大量未提交改动；未提交候选不能当作冻结基线。
- 现有业务评测脚本只评估标准化 Observation，脚本明确不调用 Agent。
- 当前业务评测样本不足以支撑稳定质量结论。
- 当前工作区没有可用项目虚拟环境；系统 Python 导入 pytest 失败于 `ModuleNotFoundError: No module named '_pytest._code.code'`，因此尚无当前测试收集或通过基线。
- 当前差异规模很大，包含跟踪文件的大量修改/删除和未跟踪文件；必须先分类为基线事实、待验证候选、明确废弃或无关改动，不能把整个脏工作区直接命名为基线。
- 环境与依赖结果必须单独记录；历史测试数和历史分数不能复用为当前事实。

---

## 3. 不可退化的产品与架构决策

### 3.1 产品边界

系统只负责**只读经营分析**：理解问题、查询受控经营数据、检索授权材料、生成证据约束的事实/假设/建议并保存可审计报告。

系统不负责：

- 自动修改经营数据库；
- 自动执行付款、采购、合同或客户变更；
- 让 LLM 决定权限；
- 在证据不足时生成确定归因；
- 将用户原始 SQL 直接交给数据库；
- 把通用聊天能力混入经营分析主链。

### 3.2 LLM 与确定性代码的职责

| 能力 | LLM 可以做 | 确定性代码必须做 |
|---|---|---|
| 意图 | 提出结构化意图候选、发现歧义 | 验证枚举、范围、必填槽位和权限 |
| 计划 | 提出步骤、查询目标和证据需求 | 限制路线、工具、次数、预算和终止条件 |
| SQL | 生成候选 SQL | AST、表/列/Join/函数/复杂度、只读执行和结果契约 |
| 指标 | 识别用户询问的指标 | 选择指标版本并计算 |
| RAG | 生成检索查询、归纳证据 | ACL、文档版本、证据身份和充足性门禁 |
| 报告 | 组织语言、生成假设与建议候选 | 数字复算、血缘、依赖、状态和唯一发布 |
| 重试 | 根据结构化错误提出修复候选 | 错误分类、次数、回退节点、预算和停止 |

原则：LLM 负责语义候选和表达；代码负责权限、计算、状态和最终发布权。

### 3.3 固定主链

~~~text
Request
  -> Task Creation + Frozen Scope + Outbox
  -> Delivery Reconciliation
  -> Atomic Claim + Lease
  -> Preflight
  -> Question Intent
  -> Analysis Plan
  -> Data Evidence / Document Evidence
  -> Evidence Barrier
  -> Report Draft
  -> Deterministic Publish Gate
  -> Persisted Result
~~~

保持受控自由 SQL、Schema Snapshot、独立只读经营库、RLS/公司范围、租约、Checkpoint 和恢复。业务 AnalysisOutcome 只有 completed / partial / insufficient_evidence；failed / cancelled 是执行终态，不是报告结果。不得改成固定查询 only、无限自主 Agent、自由辩论式多 Agent、AutoGen 全量重写、用户 SQL、LLM 权限判断或 Reviewer 直接发布。

### 3.4 对通用生产级 Agent 清单的裁剪

参考资料中的多模态、写工具确认、Saga 补偿、跨应用状态和多 Agent 协作属于通用能力，必须映射到本产品风险，而不是机械堆功能：

- 目标输入覆盖文本、业务文件和图片；文件/图片先经过隔离、MIME/大小/解压限制、恶意内容检测、解析/OCR、版本化和质量状态，不能直接进入 Prompt。音频仍需真实需求和评测数据后立项；
- 当前工具全部只读，因此重点是数据最小化、超时、幂等和证据验证，不设计付款、下单等写操作；
- Human-in-the-loop 当前用于高风险归因/建议和报告发布；若未来引入外部写工具，必须新增执行前确认、动作幂等、补偿与对账设计，不能复用只读契约；
- 事务重点是平台库任务创建/发布一致性，暂不引入面向外部写操作的 Saga；
- 当前使用 Single Workflow + 专职节点；只有评测证明上下文隔离或并行探索有收益时才增加 Agent；
- 长期记忆只保存经过治理的业务记忆，不默认把聊天记录全部向量化；
- 通用清单中与当前产品无关的功能是明确非目标，不是“遗漏后以后再堆”。

---

## 4. 目标系统分层与决定权

| 层 | 核心输入 | 核心输出 | 拥有的决定权 | 禁止 |
|---|---|---|---|---|
| API / Application | HTTP、JWT、request_id | AnalysisTaskSpec、消息、Outbox | 身份、幂等、事务 | 信任客户端 company_id；直接执行主逻辑 |
| Authorization | actor、company、resource、action | AuthorizationDecision | 当前权限和撤权否决 | LLM/Prompt 决定权限 |
| Orchestration | 冻结任务、节点结果、错误 | 状态、Checkpoint、下一节点 | 顺序、重试、停止、恢复 | 计算业务指标 |
| Planning | 问题、上下文、能力目录 | QuestionIntent、AnalysisPlan | 提出受约束候选 | 扩大工具或数据范围 |
| Data Access | QueryContract、Schema Snapshot | QueryEvidence | 只读查询、采集结果 | 将可执行当作业务正确 |
| Metric Domain | typed rows、指标定义 | CalculationResult、Fact | 公式、单位、空值、精度、血缘 | 让 LLM 算核心数字 |
| Knowledge | 检索意图、授权范围 | DocumentEvidenceSet | 检索、去重、版本、证据状态 | 先检索再 ACL；相似度当支持关系 |
| Report Domain | facts、evidence、limitations | Draft、PublishDecision | 声明分类、依赖、发布验证 | 用文案掩盖证据缺失 |
| Runtime Governance | 工具/模型请求、预算 | 调用记录、预算决定 | 版本、预算、超时、降级 | 静默换模型或无限重试 |
| Evaluation | Case、真实 Observation | Run、Bad Case、候选决策 | 基线比较与硬门禁 | 用测试数量替代业务结果 |

---

## 5. 端到端调用链与持久化边界

### 5.1 参考清单的 19 环节在本项目中的完整落地

这 19 项不是 19 个都交给 LLM 的节点，而是一条由确定性控制面包围语义模型的成熟请求生命周期。每项最终都必须有代码责任、版本化契约、失败语义和验证证据。

| # | 环节 | 本项目责任与输出 | 关键失败/兜底 | 必须证明 |
|---:|---|---|---|---|
| 0 | 用户输入 | Input Gateway 接收文本、业务文件、图片，并绑定 actor/session/conversation/request/idempotency key | 空/超限/伪造 MIME/压缩炸弹/恶意文件/重复请求在模型前拒绝或隔离 | 边界、恶意、重复和跨租户输入测试 |
| 1 | 输入预处理 | 生成版本化 NormalizedInput：语言、编码、绝对时间、业务时区、附件版本、解析/OCR 质量、截断和 provenance | 解析/OCR 失败进入 failed，恶意或硬性规则拒绝进入 rejected，不把乱码或低质量 OCR 当事实 | parser fixture、OCR 质量阈值、内容 hash 和重放 |
| 2 | 意图识别 | LLM 产生 QuestionIntent 候选；代码验证 intent、confidence、能力范围和是否需澄清 | 低置信/多意图/意图切换进入澄清或受限拆分，不猜目标 | intent/route 准确率、歧义和切换 Case |
| 3 | 参数/实体 | Slot 保存 value、type、source、confidence、required、validation；时间解析绑定 reference_time/timezone | 缺失/冲突/非法值进入澄清或稳定业务错误，默认值必须显式有来源 | 参数准确率、边界、冲突、时区 Case |
| 4 | 上下文管理 | Context Builder 从当前消息、冻结会话摘要、附件片段、任务状态中按预算选择，输出 selection manifest | 超长、旧信息、冲突和注入内容被标记/裁剪，不能改变授权 | token 预算、截断、冲突和注入回归 |
| 5 | 记忆管理 | Working State、Conversation Summary、Governed Long-term Memory 分层，记录 provenance/TTL/visibility | 未验证事实不写长期记忆；撤权/删除传播；记忆不可扩大权限 | 写入门禁、检索精度、错误记忆、TTL/删除测试 |
| 6 | 路由决策 | 确定性 Capability Router 在 direct clarification / data / knowledge / bounded workflow / review 中选择 | 未注册路线、超预算或高风险转澄清/人工，不自由扩张 Agent | 路由准确率、越权路线和 fallback Case |
| 7 | 任务规划 | Planner 输出有界 AnalysisPlan；代码验证 DAG、依赖、最大步骤、预算和结束条件 | 环、悬空依赖、重复步骤和无限循环在执行前拒绝或受限 repair | Plan contract、属性测试、停止条件 |
| 8 | 工具选择 | Tool Registry 按版本暴露最小 allowlist、能力、权限、成本和 side-effect class | 错工具、重复工具、禁用工具由策略拒绝；LLM 不能发现隐藏工具 | tool selection 准确率、allowlist、Kill Switch |
| 9 | 工具参数校验 | Adapter 校验类型/格式/业务契约；Authorization Guard 注入 company/source/document scope | 客户端或模型给出的授权字段忽略/拒绝；EMPTY deny-all | Schema、篡改、跨租户、业务边界测试 |
| 10 | 工具执行 | ToolRuntime 负责只读执行、调用幂等、并发/限流、Deadline、预算、熔断和记录 | timeout/429/断连按错误矩阵有限重试；无安全路径则停止 | 真实依赖集成、故障注入、预算和副作用证明 |
| 11 | 工具结果处理 | Result Adapter 输出版本化 QueryEvidence/DocumentEvidence，做大小限制、类型、分页、脱敏和 provenance | 空/截断/Schema 漂移/畸形结果产生明确状态，原始大结果不塞回模型 | 空值、超大、漂移、敏感字段和 hash 验证 |
| 12 | 结果验证 | Deterministic Validators 验证业务完成条件、SQL/指标/数值/引用/Claim 支持 | API 200 不等于完成；业务不正确进入 repair、partial、insufficient 或 failed | completion rate、确定性正确率、硬门禁 |
| 13 | 异常与兜底 | Error Taxonomy 驱动 retry/backoff/fallback/replan/clarify/review/terminal | 业务错误不盲重试，权限错误不 fallback，预算跨 attempt 共享 | 故障矩阵、恢复时间、重试放大率、最终一致性 |
| 14 | 用户确认/HITL | 只读产品对高风险归因/建议和发布做 draft-hash 审批；未来写工具另建确认/补偿协议 | 审批者撤权、草稿变化、重复审批和过期审批全部拒绝 | 角色、版本、重复、撤权和审计测试 |
| 15 | 最终回答 | Composer 只消费结构化事实/证据/限制；Publish Gate 决定是否公开 | 不支持的因果删除或降级；技术失败不伪装业务报告 | 格式、引用、数字、状态一致性和用户可理解性 |
| 16 | 状态持久化 | task/attempt/checkpoint/outbox/report/message/audit 通过事务和 fencing 形成可恢复状态机 | 崩溃、重复、乱序、取消和旧 Worker 写入有确定行为 | 状态迁移、并发、恢复和重复投递测试 |
| 17 | 记忆更新 | 终态后 Memory Policy 从已发布且获准内容生成候选，再确定性审批写入 | 草稿、失败、敏感、临时和未证实内容默认不写 | provenance、删除、权限与错误记忆回归 |
| 18 | 日志与可观测性 | trace/request/task/execution/model/tool/evidence/report version 全链关联，采集延迟、Token、成本和错误 | 日志脱敏；缺关联字段和采集失败可告警但不能泄露业务内容 | trace 完整率、脱敏、指标一致性、告警演练 |
| 19 | 评估与测试 | Evaluation Case -> 真实主链 -> persisted Observation -> 指标/Bad Case/晋升决策 | 开发/留出分离；硬门禁不平均；不能用单元测试数代替结果 | 单元/契约/集成/E2E/Eval/回归及证据 manifest |

顺序不是每次都线性执行：2–7 可有限迭代，8–13 可按 Plan 重复，14 按风险条件进入；但 0–1、权限/预算/状态控制、12、16、18 永远不能被模型跳过。

### 5.2 请求到任务

~~~text
conversation endpoint
  -> create_conversation_task_service
  -> authorization + data/schema/document resolution
  -> create user message
  -> create AnalysisTaskSpec snapshot
  -> create outbox event
  -> create assistant placeholder
  -> one database commit
  -> publisher attempts delivery
~~~

任务、输入消息、冻结范围、Outbox 和占位回复要么一起存在，要么一起不存在。

### 5.3 Worker 执行

~~~text
Celery delivery(task_id)
  -> atomic claim(task_id, execution_id)
  -> current authorization preflight
  -> load immutable AnalysisTaskSpec
  -> start independent heartbeat
  -> workflow node
  -> persist node output + checkpoint
  -> deterministic publish gate
  -> compare active_execution_id
  -> atomically persist report/message/terminal event
~~~

每个节点只接收上一节点的版本化结构化输出；不得依赖不可追踪的进程内隐式状态。

### 5.4 推荐节点

~~~text
preflight
  -> intent_resolution
  -> plan_validation
  -> data_evidence (optional)
  -> knowledge_evidence (optional)
  -> evidence_barrier
  -> report_composition
  -> report_validation
  -> publish
~~~

Planner、Data、Knowledge、Reviewer 可以保留为职责名称，但不是拥有最终决定权的“虚拟员工”。最终路由、状态和发布由确定性策略控制。

### 5.5 横向生产能力不是末期补丁

| 横向能力 | 必须贯穿的边界 | 对应主要工作包 |
|---|---|---|
| 安全 | 输入隔离、Prompt Injection 不可信标记、SQL/RAG 范围、日志脱敏、密钥与 Kill Switch | P0-IN、P0-A1、P0-D、P0-F、P0-G、P1-D |
| 权限 | actor/company/resource/action 决策，create/claim/tool/approve/publish 复核 | P0-A1、P0-A2、P0-F |
| 稳定性 | Deadline、有限 Retry、Fallback、Circuit Breaker、fencing、Outbox/Checkpoint | P0-B、P0-C、P0-G |
| 性能 | 异步摄取、背压、并发上限、受隔离缓存、结果大小、P95 | P0-IN、P0-G、P1-B |
| 成本 | 输入/上下文/步骤/Token/工具行数/模型调用预算，跨 attempt 共享 | P0-A2、P0-G、P1-B |
| 持久化 | PostgreSQL 权威状态、Redis 临时协调、Vector 索引、对象存储原件；任何缓存都非授权真相 | P0-IN、P0-A2、P0-B、P0-C、P1-D |
| 可扩展性 | Model/Prompt/Tool/Workflow/Metric/Schema/Input Parser/Eval 全部版本化且有兼容策略 | P0-A2、P0-G、P0-H、P1-C |
| 测试体系 | 单元、契约、属性、集成、真实 E2E、故障注入、Agent Eval、冻结回归集 | P0-0 至 P1-D |
| 运维控制 | 配置分层、readiness、告警、隔离/死信、备份恢复、回滚、灰度和 Kill Switch | P0-C、P0-G、P1-B、P1-C、阶段 10 |

这些能力随相关领域切片一起实现和验证，不能等功能写完后再统一“补安全/补测试/补日志”。

---

## 6. 核心领域契约

契约的目的不是增加类数量，而是让每个关键决定可独立验证、持久化和回放。

### 6.1 Unified Request Envelope 与 InputArtifact

请求在任何模型调用前规范成统一信封：

~~~text
request_id / idempotency_key / payload_hash
actor_id / session_id / conversation_id
received_at / original_language / business_timezone / reference_time
text_parts[] / attachment_refs[]
client_metadata_allowlist
normalization_version / safety_scan_version
input_size / truncation_decision
~~~

每个文件或图片成为版本化 InputArtifact：保存 owner/company、object key、content hash、声明和检测 MIME、大小、页数/像素/解压预算、malware/safety 状态、parser/OCR 版本、提取质量、文本/版面产物 hash、provenance 和生命周期状态。原始二进制不直接进入模型或向量库。

输入版本状态固定为 received、scanning、parsing、ready、rejected、failed。原始文件在整个扫描和解析期间位于受控 quarantine 存储区；quarantine 是存储边界，不是额外业务状态。只有 ready 版本可被任务冻结；rejected 不能通过重试绕过扫描；解析失败与恶意拒绝使用不同稳定错误码。Prompt Injection 不是靠“清洗后当作安全指令”，而是把附件内容始终标记为不可信数据，并通过指令/数据隔离、工具权限和结果门禁限制影响。

### 6.2 AnalysisTaskSpec：任务不可变事实

至少冻结：

~~~text
task_spec_id
request_id / idempotency_key
actor_id / company_id / membership_id
authorization_snapshot_version
data_source_id
schema_snapshot_id + schema_hash
document_scope_mode + resolved_document_version_ids[]
question
conversation_context_snapshot + truncation metadata
workflow_version
planner/tool/metric/prompt/model/budget policy versions
reference_time + business_timezone
created_at
~~~

约束：

- 公司、数据源和文档范围由服务器解析；
- `task_spec_id` 在持久化前由服务端生成并参与 canonical hash；数据库自增 `task_id` 只是关系投影，不进入 hash，避免先插入还是先计算 hash 的循环依赖；
- 客户端输入的 `None` 只存在于 API 解析阶段；`ALL_AT_CREATION` 必须在事务中解析成显式版本 ID，`EXPLICIT` 必须逐项授权，`EMPTY` 必须永久表示 deny-all；Worker、工具和校验器不得再接收含糊的 `None`；
- 只有不可变 DocumentVersion/ChunkVersion 建立后，TaskSpec 才能冻结 `resolved_document_version_ids`；不能用可变 document id 冒充可复现版本；
- 自动重试默认复用原快照，不静默切换最新 Schema/Prompt；
- 使用新版本必须创建显式 re-run 并关联 parent_task_id；
- 当前撤权可以阻止执行或发布，但不能修改历史快照。

输入接入还需要统一 Request Envelope：记录原始语言、时区、编码/解析结果、附件版本、request_id、conversation_id、输入大小和截断信息。空输入、乱码、超长输入、重复请求和不支持的附件必须在创建任务前返回稳定错误码。

### 6.3 QuestionIntent

~~~text
action: analyze | clarify | refuse | direct_response
analysis_kind: metric | comparison | cause | document
metric_id
dimensions[] / entities[]
current_period / comparison_period
filters[] / granularity
requested_explanation
required_evidence_types[]
ambiguities[]
slot_provenance[{slot, value, source, confidence}]
~~~

参数来源必须区分 user_message、conversation_context、system_default 和 model_inference。系统默认或模型推断的关键时间、区域和指标不得伪装成用户明确输入。确定性检查指标、维度、粒度、时间、实体和证据需求；关键槽位不完整或互相冲突时只能进入 waiting_clarification。

当前产品允许一个问题包含“指标比较 + 原因分析 + 建议”这类相关子意图，但不支持把互不相关的多个业务任务隐式合并执行。出现主题切换时创建新任务；用户中途修改目标时取消旧执行并创建关联的新任务，不能原地篡改冻结 TaskSpec。

### 6.4 AnalysisPlan

~~~text
route: data_only | knowledge_only | hybrid
steps[]
query_contracts[]
retrieval_contracts[]
required_claim_types[]
success_conditions[] / stop_conditions[]
max_model_calls / max_tool_calls / max_tokens / deadline_ms
~~~

拒绝任务范围外资源、未注册工具、无终止循环、无文档支持的原因结论、只凭文档声称精确经营数字和超预算计划。

### 6.5 MetricDefinition：指标单一事实来源

~~~text
metric_id + version
display_name
value_type / unit / currency
source_tables
measure_expression
mandatory_filters
allowed_dimensions / allowed_granularities
time_column + timezone
null_policy / zero_denominator_policy / rounding_policy
freshness_policy
owner / approved_at
~~~

“销售额”必须明确 SUM(total_amount)、只统计 delivered、使用哪个时间列、时区、币种和舍入规则，不能只是一句 Prompt。

### 6.6 QueryContract：先定义证据，再生成 SQL

~~~text
query_id
metric_definition_ref
dimensions[] / filters[]
current_period / comparison_period / granularity
required_columns[] / required_row_keys[]
result_kind / ordering / maximum_rows
null_policy / empty_result_policy / comparison_policy
expected_result_schema
~~~

SQL Candidate 关联 query_id；结果关联 SQL、Schema 和 Query Contract 指纹。

### 6.7 SQLValidationDecision

~~~text
accepted
normalized_sql_hash
referenced_tables[] / referenced_columns[]
joins[] / functions[] / wildcards[]
complexity_score / policy_version
violations[{code, location, message, repair_hint}]
~~~

稳定错误码至少包含：

- SQL_NOT_SINGLE_SELECT
- SQL_TABLE_OUT_OF_SCOPE
- SQL_COLUMN_OUT_OF_SCOPE
- SQL_WILDCARD_FORBIDDEN
- SQL_JOIN_NOT_ALLOWED
- SQL_FUNCTION_NOT_ALLOWED
- SQL_COMPLEXITY_EXCEEDED
- SQL_RESULT_CONTRACT_MISMATCH

### 6.8 QueryEvidence 与 CalculationResult

QueryEvidence：

~~~text
evidence_id
query_contract_hash / normalized_sql_hash / schema_snapshot_hash
executed_at
columns + column_types
bounded_rows
row_count / truncated
duration_ms
source_fingerprint
~~~

CalculationResult：

~~~text
calculation_id
metric_definition_ref
input_evidence_ids[]
formula
dimensions / period
current_value / comparison_value
absolute_change / relative_change
unit / currency / precision
calculation_status
limitations[]
~~~

核心计算使用 Decimal 或明确类型，不让 LLM 重算百分比。

### 6.9 DocumentEvidence

证据身份不应只依赖可变化的自增 chunk id：

~~~text
evidence_key = document_version_hash + chunk_ordinal/span
document_id / document_version / content_hash
source_path / page / section / span
company_id / minimum_role
retrieval_score / rerank_score
freshness / conflict_group
excerpt
~~~

### 6.10 Claim 与 Claim–Evidence Graph

~~~text
claim_id
type: confirmed_fact | supported_hypothesis | recommendation | limitation
statement
data_evidence_ids[] / calculation_ids[] / document_evidence_keys[]
depends_on_claim_ids[]
support_status
confidence_basis
~~~

规则：

- confirmed_fact 必须由数据证据或确定性文档事实直接支持；
- supported_hypothesis 同时关联事实和语义支持证据；
- recommendation 关联事实/假设并包含验证指标；
- limitation 说明缺什么、影响什么、下一步如何补证；
- “有引用”不等于“引用支持这句话”。

### 6.11 执行生命周期、分析结果与 PublishDecision

不得继续用一个 `status` 同时表达“任务是否还在执行”和“分析结果质量”。目标契约分为四层：

| 维度 | 允许值 | 含义 |
|---|---|---|
| ExecutionStatus | queued、running、retrying、waiting_clarification、awaiting_review、succeeded、failed、cancelled、superseded | 调度、执行与终止生命周期 |
| ExecutionStage | created、preflight、planning、querying、retrieving、validating、composing、publishing、terminal | 内部进度；不得直接成为稳定公开 API |
| AnalysisOutcome | completed、partial、insufficient_evidence | 已完成分析后的业务证据充足度；技术失败和取消不属于该枚举 |
| PublishStatus | none、draft、pending_review、published、rejected | 报告是否可对普通调用者可见 |

规则：

- `ExecutionStatus=succeeded` 必须携带一个 AnalysisOutcome；`failed/cancelled/superseded` 不得伪造业务报告；
- `partial` 表示存在可发布事实但有明确缺口，`insufficient_evidence` 表示不足以形成核心结论，两者都不是系统异常；
- `awaiting_review` 可持有不可公开草稿，但只有 `published` 才进入稳定报告字段；
- 撤权、预算耗尽、依赖错误和业务证据不足使用不同 error/outcome，不相互折叠；
- PublishDecision 逐项记录门禁版本、输入 hash、结果和拒绝原因，不只返回布尔值。

### 6.12 API、幂等与错误响应契约

API 不直接返回“模型回答成功”，而是返回稳定的任务资源：

- 创建任务：返回 202、task_id、conversation_id、request_id、queued 和轮询位置；
- 同一 user + company + conversation + idempotency_key 的相同请求返回原任务；相同 key 不同 payload 返回冲突；
- 查询任务：返回稳定 Task View，内部 Workflow State 不作为公开 API；
- 取消：只允许非终态，重复取消返回相同终态，不重新触发 Worker；
- 内部自动重试：同一 task、新 attempt、同一 TaskSpec、共享剩余预算，由状态机决定，客户端不能直接指定；
- 用户重跑：创建关联新任务和新 TaskSpec，重新解析当前权限、数据和版本，不覆盖原任务、原报告和审计链；
- 不提供含糊的“retry”公开语义；若保留旧端点，迁移期明确映射为 rerun-current，并返回新 task_id；取消任务不能按原冻结授权复活；
- 澄清：补充参数创建 child task 和新 TaskSpec，记录每个参数来源；父任务原子转为 superseded，不原地修改冻结契约；
- 报告只在 Publish Gate 通过后出现在稳定字段中，草稿与审核信息使用独立权限字段。

错误响应统一包含 error_code、message、retryable、request_id、task_id（若已创建）和 details（仅安全字段）。至少区分 input_invalid、input_not_ready、authentication_failed、authorization_denied、resource_revoked、business_contract_invalid、dependency_timeout、rate_limited、budget_exceeded、execution_conflict 和 internal_error；不得把所有异常折叠成“系统出错”。`insufficient_evidence` 通过成功执行的 AnalysisOutcome 返回，不放进技术错误码。

---

## 7. SQL 与业务计算设计

### 7.1 SQL 九层防线

1. **语法层**：单条 PostgreSQL SELECT；禁止 DDL/DML、事务和跨 Schema。
2. **目录层**：所有物理表属于冻结 Schema Snapshot。
3. **字段层**：所有字段显式存在且可暴露；默认禁止 SELECT *。
4. **Join 层**：Join 键必须属于允许关系。
5. **函数层**：只允许审核过的聚合、日期和标量函数。
6. **复杂度层**：限制子查询深度、Join/CTE 数、集合操作和估算成本。
7. **执行层**：独立只读角色、语句/连接超时和行数上限。
8. **结果层**：列、类型、唯一键、粒度、行数和空结果符合 Query Contract。
9. **语义层**：字段、公式和强制过滤符合 Metric Definition。

**可执行 SQL 只证明数据库接受了它，不证明它回答了业务问题。**

### 7.2 Schema Snapshot 目标信息

- 表、字段、类型、可空性；
- exposed / denied / sensitive 字段；
- 主键、唯一键和允许 Join；
- 允许函数与复杂度策略；
- 业务别名、枚举值和指标引用；
- 数据新鲜度、生成时间、hash 和兼容版本。

### 7.3 Fact Builder 必须成为纯函数链

~~~text
QueryEvidence
  -> normalize typed rows
  -> metric calculator
  -> calculation validator
  -> ConfirmedFact renderer
~~~

必须覆盖 NULL 与 0、零分母、负数、退款、币种、时区、舍入、截断和数据新鲜度。事实只能由已验证 CalculationResult 渲染，并能回溯输入行、公式和指标版本。

---

## 8. RAG、证据与归因

### 8.1 文档摄取

~~~text
upload
  -> authorization
  -> immutable source version
  -> parsing
  -> deterministic chunk identity
  -> metadata/ACL
  -> embedding version
  -> index activation
~~~

文档更新不静默覆盖旧证据身份；旧报告仍能说明使用的文档版本。

### 8.2 检索

~~~text
RetrievalContract
  -> current authorization prefilter
  -> query normalization
  -> lexical/vector retrieval
  -> rerank
  -> deduplicate
  -> freshness/conflict analysis
  -> sufficiency assessment
  -> DocumentEvidenceSet
~~~

必须先 ACL 过滤再产生候选，不能先跨租户检索后在应用层删除。

### 8.3 证据包与归因

RAG Tool 应返回纯证据包，不在工具内部生成最终答案。Knowledge 阶段只产生结构化声明候选，Evidence Barrier 判断是否能进入报告。

经营数据通常证明“发生了什么”，文档可能支持“为何发生”。即使实体和时间一致，也只能形成受支持假设，除非存在更强因果证据。

禁止将相关性写成唯一原因、单一来源时写确定归因、隐藏冲突或时效限制，以及把相似度或共同出现的数字当成语义支持。

---

## 9. 状态机、幂等与恢复

### 9.1 状态与阶段分离

目标 ExecutionStatus：

~~~text
queued
running
retrying
waiting_clarification
awaiting_review
succeeded
failed
cancelled
superseded
~~~

建议内部阶段：

~~~text
created
preflight
planning
querying_data
retrieving_knowledge
validating_evidence
composing
validating_report
publishing
terminal
~~~

### 9.2 不变量

1. 一个任务最多一个 active_execution_id。
2. 只有持有当前 fencing token 的 Worker 可写 Checkpoint、续租和终态。
3. cancelled 后旧 Worker 不能发布。
4. 终态报告默认不可变；审批产生新版本，不覆盖原草稿。
5. 内部自动重试不改变冻结范围；用户重跑创建派生任务和新 TaskSpec。
6. failed/cancelled/superseded 是无 AnalysisOutcome 的 ExecutionStatus；insufficient_evidence 和 partial 是 AnalysisOutcome，不能相互赋值或比较。
7. 助手消息与任务状态同事务同步。
8. 重复投递不能生成重复报告。
9. `EMPTY` 文档范围在所有层均为 deny-all，绝不能转换为 `None` 或省略过滤条件。
10. 只有当前 execution fence、当前授权和同一 TaskSpec hash 同时成立，才允许写 Checkpoint、草稿或终态。

### 9.3 状态迁移契约

每条迁移定义当前状态、事件、前置条件、下一状态、数据库副作用和外部副作用。实现时固化为参数化测试；矩阵中没有的迁移默认拒绝。

| 当前 | 事件 | 前置条件 | 下一状态 | 关键副作用 |
|---|---|---|---|---|
| queued | worker_claimed | 无 active execution | running | 创建 attempt、execution_id |
| queued | user_cancelled | 当前用户有权限 | cancelled | 消息、任务和审计同事务更新；迟到投递忽略 |
| running | retryable_failure | 仍拥有执行权、错误可重试、Deadline/预算/次数允许 | retrying | 关闭当前 attempt，预算不重置，记录 backoff |
| retrying | retry_due | 无 active execution 且未取消/撤权 | queued | 写新 generation 调度事件；重复事件幂等 |
| running | lease_expired | heartbeat 过期且仍是当前执行 | retrying | attempt=expired、清 active id、重投 |
| running | user_cancelled | 当前用户有权限 | cancelled | 消息与任务同事务更新 |
| running | clarification_required | 必填参数缺失/冲突且无安全默认 | waiting_clarification | 保存结构化缺口，不生成业务报告 |
| waiting_clarification | clarification_submitted | 当前用户有权限、payload 合法 | superseded | 同事务创建 child task、新 TaskSpec、消息和 Outbox |
| running | review_required | 草稿和确定性门禁输入已冻结 | awaiting_review | 保存 draft hash、policy version 和审核请求，不公开报告 |
| awaiting_review | review_approved | 审核者当前有权、draft hash/policy 未变、发布门禁仍通过 | succeeded | 同事务发布报告、outcome、消息和审计；不重跑分析 |
| awaiting_review | review_rejected | 审核者当前有权且请求仍 pending | succeeded | PublishStatus=rejected，保存原因；报告不公开 |
| running | publish_validated | 硬门禁通过、仍拥有执行权且 AnalysisOutcome 合法 | succeeded | outcome、报告、消息、事件同事务写入 |
| 任意非终态 | authorization_revoked | 当前权限失败 | failed | error_type=authorization_revoked；不生成报告；停止工具调用 |
| 任意非终态 | permanent_failure | 错误不可重试或预算/Deadline 耗尽 | failed | 关闭 attempt、写安全错误信封；不生成业务报告 |

### 9.4 Outbox 交付对账

published 只表示发过消息，不表示 Worker 已认领。目标：

- Outbox 使用不可变 event_id、event_type、aggregate_id 和 generation，不再对 task_id 做“每任务只能一个事件”的假设；
- `analysis_task.created` 只负责首次调度；审核批准不得伪装成再次创建任务。当前报告发布只是平台库事务，应在审批事务中绑定 draft hash、复核授权与门禁后直接完成；只有真实下游通知等外部副作用才写独立 `report.published` 事件；
- Outbox 保存 broker message id、发布时间和次数；
- Execution Attempt 保存 claimed_at；
- 已发布但长期 queued 且无 attempt 时安全重投；
- 原子认领保证重复消息只有一个成功执行；
- 重投有次数、退避、审计和死信状态；
- 终态后的迟到消息只记录 ignored。

### 9.5 租约与心跳

- 独立短事务定期续租；
- 条件包含 task_id + active_execution_id + attempt status；
- 每个外部调用 Deadline 小于剩余任务 Deadline；
- 心跳失败、失去执行权或取消后停止后续调用；
- 无法取消已发出的请求时，也不得接受迟到结果。

### 9.6 Checkpoint 兼容

Checkpoint 至少绑定 workflow_version、state_schema_version、task_scope_hash、node_name、node_contract_version、completed_output_hash 和 next_node。

只允许三种恢复：完全兼容直接恢复；存在显式迁移器后迁移；否则从安全边界重跑。不得盲目加载旧 state。

### 9.7 故障分类与重试矩阵

| 故障 | 是否重试 | 重试位置 | 必须保持 | 最终结果 |
|---|---:|---|---|---|
| LLM timeout / 429 | 有界重试 | 当前模型调用 | TaskSpec、Prompt/Schema 版本、预算 | 超限后 failed；只有已有足够可验证事实时才允许形成 partial |
| LLM 结构错误 | 最多有限 repair | 当前节点 | 原始候选、校验错误、范围 | 修复失败则该节点失败 |
| SQL 语法/契约错误 | 允许有限修复 | SQL Candidate | QueryContract、Schema Snapshot | 生成/契约错误耗尽则 failed；真实空数据才可能 insufficient_evidence |
| SQL 权限/越界 | 不重试 | 无 | 审计证据 | failed |
| 经营库/向量库短暂超时 | 有界退避 | 当前工具 | 冻结范围、幂等键、Deadline | 可形成 partial 或 failed |
| 空结果/NULL/证据不足 | 不按系统故障重试 | Evidence Barrier | 查询证据与限制 | insufficient_evidence 或 partial |
| Worker 崩溃/租约过期 | 新 attempt | 下一个兼容安全节点 | fencing、TaskSpec、Checkpoint 版本 | 恢复或 failed |
| 用户取消/权限撤销 | 不重试 | 无 | 终止事件和审计 | cancelled / failed 分别对应取消 / 撤权，均无 AnalysisOutcome |

重试计数、repair 计数、工具调用、模型调用和总成本共享任务级预算；进入新 attempt 不得重置总预算。

---

## 10. 权限、数据治理与撤权语义

### 10.1 冻结范围与当前权限同时存在

- **冻结范围**保证复现和重试不会访问新增资源；
- **当前权限否决**保证成员禁用、文档撤回、数据源停用后不能继续访问或发布。

检查时点是任务创建、Worker Preflight、每次 Data/RAG 工具调用前、人工审批前和最终发布前。当前权限只能缩小冻结范围，不能扩大冻结范围。

### 10.2 数据最小化

- Query Contract 明确所需字段，默认禁止通配符；
- Schema Snapshot 区分可查询、可聚合、可返回和禁止字段；
- 敏感值不进入普通日志、错误消息和模型上下文；
- SQL 审计默认保存 hash、表/列/Join、模板和耗时；
- 必须保留原始 SQL 时使用独立受控审计存储。

### 10.3 防御纵深

应用层范围校验是第一层，数据库 RLS/只读角色是第二层。分别证明正常 API 不越权、错误 Repository 查询仍被数据库阻止、Worker 新 Session 设置公司范围、向量 ACL 在检索阶段生效。

### 10.4 数据分类、保留与删除

- 为问题、上下文、文档、查询结果、Prompt、模型输出、日志和审计分别标注数据分类；
- 每类数据明确保留期限、删除责任、合法例外和备份中的删除传播方式；
- 用户可删除的会话记忆与依法/按制度保留的审计记录分离；
- 数据删除后，向量索引、缓存、派生记忆和对象存储副本必须同步失效；
- 模型供应商是否留存输入、是否用于训练、处理区域和子处理方属于 Model Policy；
- 不因使用加密、审计或 RLS 就宣称已经符合 GDPR、SOC 2 或 ISO 27001，合规结论需要独立证据。

---

## 11. 报告与确定性发布门禁

### 11.1 门禁顺序

~~~text
1. schema_valid
2. task_scope_valid
3. authorization_current
4. query_contract_satisfied
5. metric_lineage_valid
6. numeric_relationships_valid
7. citation_identity_and_scope_valid
8. claim_evidence_support_valid
9. recommendation_dependencies_valid
10. result_status_consistent
11. execution_ownership_valid
12. unique_publish_valid
~~~

安全或正确性硬门禁失败时不得发布。Reviewer 的“通过”不能覆盖确定性失败。

### 11.2 人工审核

人工审核用于低置信归因、证据冲突、高风险业务建议和新型 Bad Case，不用于修补所有模型错误。

审核记录 reviewer、输入报告版本、决定、理由、修改 diff、时间和最终版本。审批不能把越权内容变成合法内容。

---

## 12. 模型、Prompt、上下文与工具治理

### 12.1 运行版本指纹

~~~text
provider / model / model_parameters
prompt_template_id + prompt_hash
structured_output_schema_version
workflow_version
tool_contract_version
metric_catalog_version
retrieval_config_version
embedding/reranker version
~~~

空 prompt_version 不能支撑可复现声明。

### 12.2 上下文分层

~~~text
System policy
  -> frozen task scope
  -> current question
  -> bounded conversation snapshot
  -> planner memory
  -> tool/evidence results
~~~

每层保存来源、Token/字符预算和截断元数据。历史助手内容、文档和工具输出均视为不可信数据，不能覆盖权限与工具规则。

Working Memory 只保存当前执行所需的版本化 Workflow State，并随 Checkpoint 持久化。Conversation Memory 只装载有限轮次、完成或部分完成的可信历史结果。长期业务记忆必须有来源、公司范围、创建者、版本、TTL/失效条件、可见角色、冲突状态和删除机制；未证实假设不得提升为长期事实。

上下文选择策略必须可以测试：保留当前问题和冻结范围，按预算装载最近消息与相关记忆，保存截断原因；不能仅按“最近 N 条”声称上下文正确。要用同一评测集测试短历史、长历史、冲突历史和恶意历史下的退化。

### 12.3 模型回退与工具契约

只有错误可重试、备用模型满足相同结构契约、不扩大范围、预算和 Deadline 允许且记录实际版本时才回退。业务校验失败不得通过盲目换模型无限尝试。

工具集保持小而明确。每个工具定义适用/不适用任务、服务器注入范围、模型可填参数、结构化结果、稳定错误码、可重试性、修复提示、超时/行数/次数限制和敏感信息策略。

### 12.4 运行时控制面

以下能力属于系统设计，不是部署附属项：

- API、用户、公司、模型和工具分别限流，JWT 请求不能绕过限流；
- 工具调用按错误类别配置 timeout、backoff、jitter、circuit breaker 和 fallback；
- 缓存键必须包含 company、权限范围、Schema/文档/模型/Prompt/工具版本，敏感结果默认不跨任务缓存；
- 支持 disable_tool、disable_model、disable_feature 和 stop_new_tasks 的 Kill Switch；
- Kill Switch 与熔断只阻止新调用，运行中任务按状态机安全停止或降级；
- 所有上限包含 max_steps、max_tool_calls、max_model_calls、max_tokens、max_cost 和 max_runtime；
- 并发会话通过 task version / optimistic lock 处理，不能让两个终端静默覆盖同一任务意图。
- Data 与 Knowledge 只有在输入依赖独立、权限/预算分别冻结、结果可确定性合并且取消可传播时才能并行；是否并行由 P95 与质量对比决定。

### 12.5 配置与变更控制

- 配置分为安全策略、业务契约、模型策略和环境连接，不使用一个无边界 settings 对象贯穿所有层；
- 安全硬门禁不能被普通运行参数关闭；紧急例外必须审批、到期并审计；
- 配置启动时做 Schema 校验和交叉约束校验，非法组合阻止进程 Ready；
- 运行任务保存实际配置快照或不可变版本引用，不能只记录当前环境变量；
- Kill Switch、模型切换、Prompt 切换、指标口径变化和工具版本变化都产生治理事件；
- Secret 只通过运行环境注入，日志、Prompt、Checkpoint、评测产物和错误响应不得包含 Secret。

---

## 13. 可观测性与审计

### 13.1 统一关联链

~~~text
request_id
  -> conversation_id
  -> input_artifact_version_id / task_id / task_spec_id
  -> outbox_event_id
  -> execution_id / attempt_id
  -> workflow_event_id
  -> tool_call_id / model_call_id
  -> checkpoint_id
  -> evidence_id / report_version
~~~

系统必须能回答：为何选择该路线、用了哪些冻结资源和当前权限、哪个 SQL/指标版本产生数字、哪个文档版本支持哪个假设、为何重试/停止/审核、哪个执行拥有发布权、本次消耗多少调用/Token/时间/成本。

### 13.2 指标

- Trusted Business Analysis Success Rate；
- intent/route/entity/period accuracy；
- SQL result equivalence；
- metric calculation correctness；
- claim support precision；
- citation scope correctness；
- ExecutionStatus 的 succeeded/failed/cancelled/superseded 比例，与 succeeded 内 AnalysisOutcome 的 completed/partial/insufficient_evidence 比例分别统计；
- queued age、claim latency、lease expiry、recovery success；
- duplicate delivery/publish、stale write rejected；
- P50/P95 总延迟和节点延迟；
- 每任务模型调用、Token、成本；
- 权限与确定性门禁事件。

默认只保存必要结构化元数据，不保存完整 Prompt、文档块、查询结果和敏感 SQL 字面量。

---

## 14. 生产级评测体系

### 14.1 评测真实业务结果

~~~text
输入问题
  -> 真实权限与冻结范围
  -> 真实 Worker
  -> Planner/SQL/Retrieval/Calculation artifacts
  -> persisted report
  -> normalized EvaluationObservation
  -> deterministic metrics
  -> calibrated semantic judgment
~~~

在现有 EvaluationCase / Observation / Run 上增加：

- DatasetManifest：数据集、Schema、文档、业务库版本和来源；
- Observation Adapter：只从持久化真实任务生成 Observation；
- Run Fingerprint：代码、脏工作区、模型、Prompt、工具、指标和环境；
- CandidateDecision：晋升、退化、Bad Case、回滚和未证明范围。

### 14.2 数据集

早期使用 20–30 个真实 Case；成熟比较至少 50 个。按难度、data/knowledge/hybrid、正常/空/NULL/零分母/冲突/过期、权限/注入、超时/重复/崩溃/恢复、同义改写和长上下文分层。

开发集用于调试；冻结留出集不得进入 Prompt、常量或优化分析。自动从语料生成的问题只能发现候选 Case，不能直接充当可信 Gold。

### 14.3 指标分层

硬门禁必须为 0：

- 跨公司或任务范围外数据；
- 越权文档；
- 经营库写入；
- 编造数字或无证据确定归因；
- 重复报告；
- 取消后完成写入；
- 旧 Worker 覆盖新结果；
- 绕过确定性校验发布。

确定性质量指标至少分开报告：输入解析成功率与拒绝准确率、意图识别准确率、路由/工具选择准确率、参数/实体准确率、Plan 契约通过率、SQL 结果等价率、指标计算/数字关系正确率、引用身份与范围正确率、任务完成率、结果状态正确率和恢复不变量通过率。

语义质量指标包括 Claim–Evidence 支持准确率、关键事实完整率、无支持声明率/幻觉率、建议可验证性和限制说明充分性。运行指标分开报告恢复成功率/恢复时间、重复执行率、P50/P95 延迟、Token、模型/工具调用次数和成本。

EvaluationObservation 必须保留 expected query requirements、实际 route/tool/parameter/plan artifacts、所有硬门禁明细和资源范围。空 `allowed_chunk_ids` 必须表示不允许任何 chunk，不能解释为 allow-any；`hard_gate_passed` 是所有适用硬门禁的逻辑 AND，不得只检查一个汇总字段。任何 substring 匹配只能作为低成本 smoke，不能作为最终业务正确性证据。

LLM Judge 只在确定性门禁通过后评语义，并需人工校准。单一总分不能掩盖关键维度失败。

### 14.4 北极星指标

Trusted Business Analysis Success 是合取条件：

~~~text
correct scope
AND correct business intent
AND equivalent SQL/result semantics when data is required
AND reproducible calculations
AND supported claims
AND correct outcome state
AND deterministic publish gate passed
AND within approved budget
~~~

### 14.5 候选晋升

每次只改变一个主要变量。候选成为基线前保存：

1. baseline/candidate 配置；
2. 相同数据集和环境；
3. 开发集与冻结留出集结果；
4. 硬门禁；
5. P95、Token 和成本；
6. 新增/消失 Bad Case；
7. 退化分析；
8. 回滚方式；
9. 未证明范围。

---

## 15. 版本化与演进

必须版本化 Workflow state、Planner/Query/Report contract、Prompt、Model policy、Tool contract、Metric catalog、Schema Snapshot、文档/chunk/index、Embedding/reranker、Evaluation dataset 和 Publish gate。

运行中任务默认使用创建时版本；撤权和紧急禁用可即时否决；结构不兼容时创建新任务或从安全边界重启；回滚不改历史报告；数据/文档变化后的重跑形成新报告版本并可比较。

当前项目尚未冻结对外 v1，因此允许为了正确性进行一次明确的破坏性契约整理，不为教学历史保留错误兼容层。每项破坏性修改必须先写 ADR，并选择迁移方式：

- 可无损回填：expand -> backfill -> verify -> switch read/write -> contract；
- 无法可信回填：旧记录标记 `legacy_unverifiable`，只读保留，不允许恢复或重新发布；
- 需要维护窗口：明确停写范围、备份点、前滚/回滚条件和不可逆边界；
- API 在 ExecutionStatus、AnalysisOutcome、错误信封和幂等语义稳定后冻结 v1；之后的破坏性修改走新版本和废弃周期。

“能删改”不是随意重写。保留与否由不变量、故障模型、迁移成本、验证证据和回滚能力决定，而不是由旧代码量决定。

---

## 16. 分阶段实施顺序

本节是唯一权威顺序；18.1 的 Work Package 只展开同一顺序，不再维护第二套阶段计划。阶段按安全不变量和依赖排列，不按“学习一个框架”排列。部署仍只在最后。

### 阶段 0：工程接管与可运行证据基线（P0-0）

1. 建立可复现 Python/依赖环境，使测试至少能成功收集；
2. 分类当前巨大工作区差异：已验证事实、待验证候选、明确删除、无关用户改动；
3. 保存 HEAD、dirty diff hash、依赖锁、迁移 head、配置指纹、数据/模型替身和真实依赖边界；
4. 建立最小 Observation Adapter 和硬门禁 smoke，先能比较当前主链，再优化候选；
5. 记录不能运行的验证及根因，绝不借用历史测试数。

门禁：当前任务已审计为 **未 ready**。只有测试环境可收集、差异已分类、基线 manifest 可重建且 smoke 产物可追溯，才进入契约实现。此阶段是工程验证，不是部署工作。

### 阶段 1：统一输入治理与领域语义（P0-IN、P0-A0）

先建立文本/文件/图片的统一 Request Envelope 与隔离摄取状态机，再通过 ADR 冻结 ExecutionStatus / ExecutionStage / AnalysisOutcome / PublishStatus、错误信封、幂等键、Retry/Rerun、文档范围代数和 API 版本策略。建立数据库迁移、旧值映射和不可验证旧记录策略。

门禁：恶意/超限/伪造/低质量输入不能进入 Prompt 或可检索索引；原件、解析结果和 OCR 结果有版本与 provenance；不存在同一字符串在不同层表达不同含义；未定义迁移的旧状态不能进入 Worker；同 key 同 payload 重放、异 payload 冲突可由数据库约束证明。

### 阶段 2：权限止血与不可变资源身份（P0-A1、P0-A2）

先修复空文档范围扩大、客户端/模型传入授权范围和工具层 fail-open；再引入不可变 DocumentVersion/ChunkVersion、TaskSpec id/hash、运行版本指纹、五个授权检查点和服务端注入的 AuthorizedExecutionContext。未挂载旧 `/tasks` 作为死代码删除或明确封存，不把它误称为当前公开旁路。

门禁：空范围 deny-all；文档/数据源撤权立即否决；旧内容仍可按版本审计；伪造范围无效；旧任务无可信快照时只能只读和 rerun-current。

### 阶段 3：状态、交付与恢复控制面（P0-B、P0-C）

实现统一 Transition Service、execution fencing、独立心跳、任务/节点/调用 Deadline、兼容 Checkpoint、事件 generation、delivery/claim 对账、死信/隔离和人工处置；审核批准直接走受保护的终态事务，不复用创建事件或重跑分析。

门禁：重复/乱序消息不重复报告；安全节点崩溃可恢复；旧 Worker、取消后和撤权后的全部写入被拒绝；published-but-unclaimed 可对账恢复；毒消息进入可审计隔离而非无限重投。

### 阶段 4：确定性查询、指标与事实链（P0-D、P0-E）

实现 QuestionIntent、AnalysisPlan、MetricDefinition、QueryContract、Schema Snapshot 列/Join/函数约束、SQL AST 硬行数上限、连接/语句 Deadline、结果类型/粒度/唯一键校验、typed calculator 和完整数值血缘。

门禁：可执行但语义错误的 SQL 被拦截；已有超大 LIMIT 也不能突破预算；核心数字由确定性代码复算；NULL/0/负数/舍入/单位/时区有明确契约。

### 阶段 5：文档证据、Claim 支持与发布（P0-F）

实现稳定 evidence key、当前 ACL 前置检索、纯证据包、时效/冲突/充足性、Claim–Evidence Graph、草稿 hash 审批和唯一 Publish Gate。

门禁：命中不等于支持；冲突与证据不足诚实表达；不输出无证据唯一因果；撤回文档不能被新任务读取，历史报告仍能按版本审计。

### 阶段 6：工具/模型运行时治理（P0-G）

完成小而稳定的工具协议、服务器注入范围、结构化错误、调用幂等、超时、预算、有限 fallback、熔断、Kill Switch、敏感日志策略和实际版本记录。

门禁：范围不能由 LLM 扩大；预算跨 attempt 不重置；依赖故障不会形成无限重试或静默弱化确定性门禁；原始 SQL/敏感字面量不进入普通日志。

### 阶段 7：真实业务评测与候选晋升（P0-H）

把阶段 0 的 smoke 扩为真实 Worker -> persisted task -> Observation Adapter；先建立 20–30 个可审查开发 Case，再扩展 50+ 并冻结留出集；分离硬门禁、确定性正确性、业务结果、可靠性、性能和成本；维护 Bad Case ledger。

门禁：评测调用真实主链和声明的真实依赖；所有安全/正确性硬门禁为零；候选在留出集和故障集无不可接受退化；阈值依据阶段 0 基线和业务风险设定，不在无数据时编造。

### 阶段 8：上下文、数据生命周期与持续治理（P1-A、P1-D）

实现有界上下文和记忆 provenance、TTL/删除/冲突语义，以及文档、chunk、embedding、审计、报告、备份和评测样本的分类、保留、删除传播、legal hold 和隐私导出。

门禁：删除能传播且可证明；审计保留与内容删除边界明确；旧记忆和跨租户记忆不能污染新执行。

### 阶段 9：性能、成本、审核与事故闭环（P1-B、P1-C）

在可信评测上优化缓存、并发、背压、P95 和成本；完成高风险审核、事故分级、隔离/恢复、回滚和再评测。长期运行验收的样本量与观察窗口在阶段 0 基线后写入 SLO，不预先虚构数字。

门禁：性能优化不破坏隔离、正确性和可恢复性；一次事故能从告警到止血、根因、修复、回归、候选晋升和审计导出闭环。

### 阶段 10：最小发布验证（非主线）

只验证干净启动、迁移、真实 PostgreSQL/Redis/Worker/业务库/向量/模型 E2E、密钥不入库、备份恢复、所有关键依赖 readiness 和阶段 9 已定义的基本容量/P95。

不引入 Kubernetes、服务网格、多区域和微服务，除非真实容量或可用性证据证明单节点不能满足明确目标。

---

## 17. 当前代码到目标的修改地图

| 模块 | 首要修改 | 验收 |
|---|---|---|
| API input / document ingestion / object storage | Unified Request Envelope、文件/图片隔离、扫描、解析/OCR、版本与 provenance | 恶意/超限/低质量输入不进入 Prompt/索引；ready 版本可重放 |
| models + Alembic migrations | 状态/结果拆分、InputArtifact、DocumentVersion、TaskSpec、Outbox generation、幂等约束 | 前滚/回滚/旧数据映射和 legacy_unverifiable |
| services/conversation_service.py | 幂等、显式范围代数、完整任务版本/授权快照 | 事务、同 key 冲突、EMPTY deny-all、服务端范围 |
| services/outbox_service.py | 多事件类型/generation、认领对账、重投、死信 | created 事件不被审批复用；published 未 claimed 可恢复；下游事件按副作用幂等 |
| services/task_execution_service.py | 统一迁移、独立心跳、fencing、Checkpoint 兼容 | 崩溃、超时、取消/撤权、旧 Worker |
| services/workflow_graph.py / nodes | 明确 Preflight、Evidence Barrier、Publish Gate | 有限路由、版本化节点输出 |
| schemas/query_contract.py | 完整查询和结果语义 | 可判定是否回答业务问题 |
| tools/validator.py | 列/Join/函数/复杂度/通配符/语义 | 错 SQL 执行前拒绝 |
| tools/snapshot_catalog.py | exposed/denied/sensitive、函数、指标、版本 | 最小数据访问 |
| services/fact_builder.py | typed calculator + lineage | 数字可重算 |
| core/rag 与 vector repository | 稳定证据、ACL、版本/冲突/时效 | 检索与声明支持分离 |
| schemas/final_analysis.py | Claim、Calculation、evidence key、insufficient | 事实/假设/建议边界 |
| services/report_validator.py | 完整确定性发布门禁 | Reviewer 不可绕过 |
| services/citation_validator.py | 为 Claim Support 提供验证输入 | 支持关系可评测 |
| services/numeric_validator.py | 公式、关系、单位、血缘 | 不只检查数字出现 |
| business evaluation | Observation Adapter、Manifest、Decision | 真实链路与冻结留出集 |
| services/review_service.py | 审批绑定 draft hash/policy/current authority，并在单事务发布 | 重复/过期/撤权审批不重跑分析且不重复发布 |
| api/tasks.py / router | 删除、封存或适配旧路径 | 唯一任务主链 |

---

## 18. 全项目生产化执行程序：不以单一业务案例为中心

生产化的实施单位不是“做完一道销售分析题”，而是一个能贯穿真实主链、消除一个系统性风险、具备故障与回滚证据的 Work Package。业务问题只是验收数据，不能决定系统边界。

每个 Work Package 不要求机械修改所有层；它必须列出受影响与不受影响的边界，并沿受影响链追踪 API/服务端事实/持久化/异步/工具/权限/终态/审计。完成证据至少包括本包契约与故障测试，以及整条主链非退化 smoke。只新增一个 Pydantic 类、Prompt、Agent 节点或单元测试，不能独立算作生产化完成。

### 18.1 生产化工作包与依赖顺序

| ID | 工作包 | 消除的系统性风险 | 依赖 | 完成证据 |
|---|---|---|---|---|
| P0-0 | 工程接管、可运行环境与评测 smoke | 在未知 dirty tree、坏依赖和历史指标上继续堆候选 | 无 | 可重建环境、测试收集、差异分类、baseline manifest、真实主链 smoke |
| P0-IN | 文本/文件/图片输入网关与隔离摄取 | 恶意、超限、伪造或低质量内容直接污染 Prompt/索引 | P0-0 | MIME/大小/解压/OCR/隔离/版本/provenance/重复输入测试 |
| P0-A0 | 状态/结果/API/幂等规范化 | 同名状态语义冲突、重放重复创建、破坏性迁移无边界 | P0-IN | ADR、数据库约束、迁移回放、旧值映射、API 契约测试 |
| P0-A1 | 权限范围止血与服务端注入 | 空文档范围扩大、模型/客户端影响授权范围 | P0-A0 | EMPTY deny-all、跨公司/越权/撤权、工具参数篡改测试 |
| P0-A2 | 不可变资源版本与任务权威链 | 可变文档、旧上下文或重试破坏复现与执行范围 | P0-A1 | DocumentVersion/ChunkVersion、五点授权、TaskSpec id/hash、legacy 路径 |
| P0-B | 统一状态迁移、Execution fencing 与 Deadline | 旧 Worker、取消后结果、并发迁移覆盖新状态 | P0-A2 | 状态契约测试、并发测试、迟到写入拒绝、超时终止 |
| P0-C | Outbox delivery/claim 对账与恢复 | published 但未认领导致任务永久 queued | P0-B | 丢消息、重复消息、Broker 恢复、死信和人工处置演练 |
| P0-D | Query Contract、指标目录与 SQL 九层防线 | SQL 可执行但业务语义错误或越界 | P0-A2 | 列/Join/粒度/指标/复杂度/只读/租户范围的拒绝 Case |
| P0-E | Typed Calculation、数据血缘与数值校验 | LLM 算错、单位混淆、数字无法复算 | P0-D | QueryEvidence -> CalculationResult -> ConfirmedFact 可重放 |
| P0-F | 文档证据、Claim–Evidence Graph 与发布门禁 | 检索命中被误当作结论支持或确定归因 | P0-A2、P0-E | 越权、冲突、过期、注入、证据不足和错误引用 Case |
| P0-G | Tool/Model 错误协议、预算、熔断与降级 | 无限重试、成本失控、依赖故障扩散 | P0-A2、P0-B | 故障矩阵、预算不重置、Fallback 轨迹、Kill Switch |
| P0-H | 真实 Observation、评测、审计与基线晋升 | 测试通过却不知道业务质量是否提升 | P0-C–P0-G | 真实 Worker E2E、冻结留出集、Bad Case、候选决策 |
| P1-A | 有界上下文、会话/长期记忆治理 | 旧信息、越权记忆和上下文膨胀污染决策 | P0-A2、P0-F | provenance、TTL/删除、冲突、截断和权限回归 |
| P1-B | 缓存、并发、性能与成本控制 | 跨租户缓存、热点任务和长尾延迟 | P0-G、P0-H | 隔离键、并发上限、P95、Token/成本和失效测试 |
| P1-C | 审核、事件响应与持续治理 | 高风险结论无人负责，事故不能闭环 | P0-H | 审核版本链、事故演练、回滚、再评测和审计导出 |
| P1-D | 数据生命周期、隐私与删除传播 | 内容已删但 chunk/embedding/报告/备份/评测仍泄露 | P0-A2、P0-H | 数据分类、保留、删除证明、legal hold、隐私导出和备份边界 |

这里的 P0/P1 表示风险优先级，不表示 P1 可以永远不做。P0-0 先建立“能证明当前事实”的地基，P0-H 才完成可信优化闭环；P1 完成后，系统才具有较成熟的长期运行与治理能力。

### 18.2 首个实施批次：P0-0 工程接管与基线

在计划核对完成后，第一批仍不修改生产逻辑。先修复验证环境、分类现有差异、冻结可重建 manifest，并让最小评测 smoke 能从真实持久化结果生成 Observation。当前 pytest 无法导入且工作区未分类，所以本计划此刻仍处于 `proposed`，不能跳过 P0-0 直接开始 P0-A。

P0-0 最低产物：

1. 可重建的依赖环境与成功的 test collection 记录；
2. HEAD、dirty diff、未跟踪文件、迁移 head、配置和依赖 fingerprint；
3. 每组现有改动的 owner、意图、保留/删除/候选分类，不擅自覆盖用户改动；
4. 当前主链 smoke Observation、硬门禁结果和所有未运行的真实依赖边界；
5. 从此基线安全回到原代码/数据的操作步骤，但未经用户明确要求不自动 commit 或清理工作区。

### 18.3 P0-IN 设计包：文本、文件和图片输入治理

目标管线：

~~~text
HTTP metadata + streamed body
  -> authenticate + request/idempotency decision
  -> enforce transport/type/size/count/decompression/pixel/page budgets
  -> quarantine original object + content hash
  -> MIME magic / malware / parser safety checks
  -> sandboxed parser or OCR
  -> normalized text/layout/table blocks + quality/provenance
  -> immutable InputArtifactVersion
  -> ready | rejected | failed
  -> only ready versions may enter TaskSpec/context/index
~~~

关键设计：

- 支持格式由版本化 InputType Registry 决定；扩展名、客户端 Content-Type 和实际 magic 分开记录，冲突时拒绝或隔离；
- 上传采用流式限制，不能先完整读入内存再检查；压缩包、PDF 页数、图片像素和解析时间分别有预算；
- parser/OCR 输出是候选内容，保存 parser/model/version/quality/page-region provenance；低质量结果必须提示或拒绝，不能静默当事实；
- 附件中的“忽略系统规则”等文本始终属于 untrusted content。检测只用于标记、隔离和评测，真正安全边界仍是上下文分区、工具授权、服务端范围和发布门禁；
- 原件、解析产物、chunk 和 embedding 使用不同生命周期与访问权限；删除和保留由 P1-D 完成全链治理；
- 同一 payload hash 可去重存储，但授权、owner、公司和引用关系不能因去重跨租户共享；
- 异步解析时，任务只能等待明确的 ready 版本或返回可操作状态，不能在“可能解析完成”的竞态下启动。

验收至少覆盖：空文本、超长文本、编码错误、扩展名/MIME/magic 冲突、恶意文件、压缩炸弹、超页/超像素、解析超时、OCR 低质量、Prompt Injection、重复上传、跨公司 hash 相同文件、解析后撤权、删除传播和 parser 版本重放。

### 18.4 P0-A 设计包：状态、范围、资源版本与任务权威链

P0-A0/A1/A2 不改模型效果，也不以某个业务指标问题为中心。它们建立所有后续能力依赖的执行权威边界：**任务处于什么生命周期、为什么被允许创建、允许访问哪些不可变资源、以哪些版本运行、何时必须停止，以及谁有权发布结果。**

当前真实调用链是：

~~~text
api/conversations.py
  -> create_conversation_task_service(context, content, document_ids, request_id)
  -> create_task(user_id, company_id, data_source_id,
                 schema_snapshot_id, document_ids, context_snapshot)
  -> create_analysis_task_event(task_id)
  -> publish_analysis_task_event(event_id)
  -> Worker claim_execution(task_id, celery_task_id, worker_id)
  -> workflow_graph / ToolRuntime
  -> finish_execution(execution_id, result)
~~~

已有事实：创建服务会按当前公司、角色、可见文档、ready 数据源和激活的 Schema Snapshot 解析范围；任务、消息和 Outbox 在同一事务写入；Worker 使用 execution_id、租约和 Checkpoint。已确认的危险缝隙是：创建时 `None` 可表示全选，但冻结后的空 document id 列表在 Worker/RAG/报告校验中可退化成“不传过滤条件”；文档内容又会原地变更。系统仍缺少不可变资源版本、完整 TaskSpec、统一状态语义和五个检查点共用的授权协议。

目标链为：

~~~text
HTTP input
  -> InputNormalizer
  -> TaskAuthorityResolver(current actor/company/resources)
  -> resolve DocumentScope to immutable DocumentVersion ids (EMPTY stays deny-all)
  -> AnalysisTaskSpecBuilder
  -> persist task_spec_id + task_spec_version + task_spec_snapshot + task_spec_hash
  -> task/message/outbox atomic commit
  -> ClaimPreflight(current authority + frozen scope + runtime compatibility)
  -> AuthorizedExecutionContext
  -> ToolAuthorizationGuard on every call
  -> PublishAuthorizationGuard + deterministic gates
  -> one fenced terminal transaction + audit event
~~~

#### AnalysisTaskSpec 最低字段

| 分组 | 字段 | 规则 |
|---|---|---|
| 规范身份 | task_spec_id、task_spec_version | task_spec_id 在插入前生成并参与 hash；关系型 task_id 不进入 hash |
| 请求身份 | actor_id、company_id、membership_id、role_at_create、auth_version | 全部由服务端解析；快照只用于审计，当前撤权可否决 |
| 输入 | normalized_question、input_message_id、conversation_id、context_snapshot_hash | 原始文本受长度/编码限制；上下文视为不可信数据 |
| 数据范围 | data_source_id、schema_snapshot_id、schema_fingerprint | 冻结到任务；数据源禁用时 fail closed |
| 文档范围 | scope_mode + resolved_document_version_ids + content/index hash + min_role | API 的 None 已被消歧；EMPTY deny-all；每次检索仍检查当前 ACL/撤回状态 |
| 运行版本 | workflow、prompt、model policy、tool contract、metric catalog、publish gate version | Checkpoint 仅能由兼容版本恢复 |
| 控制预算 | task_deadline、node/tool/model timeout、max attempts、token/cost/tool-row budget | 重试继承剩余预算，不能重置总预算 |
| 幂等关系 | idempotency_scope、request_id、request_payload_hash、parent_task_id、run_mode | 数据库唯一约束；同 key 同 payload返回原任务；同 key 异 payload 返回冲突 |
| 完整性 | task_spec_version、canonical serialization、task_spec_hash | 认领和发布前重算；不一致立即停止并记录安全事件 |

关系列 `company_id`、`data_source_id`、`schema_snapshot_id` 仍保留用于外键、索引和 RLS；`task_spec_snapshot` 是可审计的完整运行契约。两者不允许各自演化：由唯一 Builder 同时产生，Preflight 校验关系列与快照一致。`task_spec_id` 在 flush 前生成；`task_id` 只做关系引用。旧任务若无法无损回填，不伪造 TaskSpec；允许只读查看，但不能恢复或重新发布，只能创建一条使用当前权限与版本的新任务。

#### 五个权限检查点

| 检查点 | 冻结事实 | 必须检查的当前事实 | 失败行为 |
|---|---|---|---|
| create | 用户请求和服务端解析范围 | 用户、成员、公司、数据源、文档可用 | 不创建任务，不写 Outbox |
| claim | 完整 TaskSpec | 成员仍有效、数据源未禁用、版本可运行 | fail closed；可恢复故障与撤权分开记录 |
| tool | 该工具允许的最小资源范围 | 当前 ACL、租户、只读策略、Kill Switch | 工具调用拒绝且不可由 LLM 重试绕过 |
| approve | 草稿和审核请求范围 | 审核者角色、任务/公司归属、草稿版本 | 审批无效，不重投 |
| publish | TaskSpec、execution_id、证据和草稿版本 | 当前授权、执行所有权、确定性门禁 | 不写完成结果；旧 Worker 全部拒绝 |

#### P0-A0/A1/A2 必须先写的行为契约

1. 客户端提交 `company_id`、角色、Schema 或文档权限字段时，服务端忽略或拒绝，不能扩大范围；
2. ALL_AT_CREATION 在创建事务内解析为显式版本集合；EXPLICIT 逐项授权；EMPTY 在 Worker、RAG、引用校验和评测中一律 deny-all；
3. 同一幂等作用域和 key、相同 payload 只产生一个任务、一个用户消息和一个待发布事件；payload 不同返回稳定冲突码；
4. 角色降低、成员禁用、文档撤回或数据源禁用发生在创建后时，后续检查点立即 fail closed；
5. 自动 Retry 只为技术性失败在同一 task 内创建新 attempt，复用 TaskSpec 与剩余预算；公开 Rerun 使用当前数据、权限和版本创建新 TaskSpec，并关联父任务；
6. execution_id 不匹配、租约失效、任务已取消或 TaskSpec hash 不一致时，任何 Checkpoint、失败状态和最终报告写入都被拒绝；
7. 授权服务或数据库不可用时不降级为允许；记录可恢复故障，不错误标记为业务证据不足；
8. 旧任务缺少完整快照时不静默补默认值；进入明确的 `legacy_unverifiable` 兼容路径；
9. 未挂载的 `/tasks` 旧模块按死代码删除或封存；若未来重新挂载，必须走同一 Application Service 和契约测试。

#### P0-A0/A1/A2 验收矩阵

| Case | 预期持久化结果 | 预期外部行为 |
|---|---|---|
| 正常创建 | TaskSpec、hash、消息、Outbox 同事务存在 | 202/已存在任务引用 |
| 同 key 同 payload 重放 | 无新增行 | 返回原任务 |
| 同 key 不同 payload | 无新增行，记录冲突事件 | 稳定 409 错误码 |
| 伪造其他公司/文档 | 无任务、无 Outbox | 404/403，不泄露资源存在性 |
| 无可见文档或显式空集合 | TaskSpec 保存 EMPTY，版本集合为空 | RAG 零结果且不发无范围查询；报告不能引用任何 chunk |
| 创建后成员被禁用 | Claim 或下一检查点拒绝 | 明确撤权终止，不进入 LLM |
| 工具前文档撤回 | 无越权 ToolCall 成功记录 | 拒绝检索；报告不得引用旧内容 |
| 执行后发布前撤权 | 不写 completed/partial 报告 | 终止并保留审计证据 |
| 旧 Worker 迟到 | 新执行和任务结果不变 | fenced rejection |
| 旧任务无完整 Spec | 不伪造版本或 hash | 只读；提示创建新任务 |
| 授权依赖暂时故障 | 不发布、不扩大权限 | 可恢复失败；有界重试后停止 |

完成 P0-A0/A1/A2 的含义只是“后续模块有了可信执行边界”，不是整个项目已经生产级。随后按 18.1 的依赖顺序持续推进，直到 P0-H 与 P1 的长期治理门禁都有证据。

### 18.5 全链兜底梯子

兜底不是一句“稍后重试”，而是有顺序、有预算、有终态、有审计：

1. 输入非法或超限：API 直接拒绝，不调用 LLM；
2. 意图歧义或缺关键参数：`waiting_clarification`，保留已知参数来源，不猜值；
3. 当前权限、范围或完整性无法确认：fail closed，不用缓存权限兜底；
4. 数据源/Schema/文档未准备好：返回可操作错误，不让 Planner 编造替代事实；
5. 工具瞬时故障：同执行内有界退避；超预算后熔断，不切换到越权或非只读工具；
6. 模型超时/限流/结构错误：按版本化策略切换模型或一次受限修复；确定性门禁不随降级放宽；
7. 数据存在但不完整：产出 `partial` 或报告级 `insufficient_evidence`，明确缺口；
8. 证据不支持归因：保留可复算事实，删除不受支持的原因，不用常识补齐；
9. Worker/Broker 崩溃：由 Outbox 对账、租约、Checkpoint 和 fencing 恢复；预算与 TaskSpec 不重置；
10. 取消、撤权、Kill Switch 或旧执行迟到：立即停止后续副作用，所有迟到写入拒绝；
11. 高风险且证据允许但需要责任确认：进入 `awaiting_review`，审批绑定草稿 hash 和审核版本；
12. 无安全降级路径：进入稳定失败终态，保留诊断和重跑入口，绝不伪造成功。

---

## 19. 成熟稳定的交付与教学闭环

教学只改变“谁先完成高学习价值工作”，不降低工程门禁。每个 Work Package 使用同一交付状态机：

~~~text
proposed
  -> ready
  -> implementing
  -> candidate_verified
  -> adopted | rejected
  -> monitored
  -> superseded
~~~

- `proposed`：只有问题和假设，不能写“计划完成”；
- `ready`：基线、范围、契约、失败矩阵、验证命令和回滚已明确；
- `implementing`：实现与候选证据允许变化，但不得覆盖基线；
- `candidate_verified`：本包适用的开发集、故障注入、真实依赖 E2E 和冻结留出集均有产物；不适用项必须写理由，不能伪造空报告；
- `adopted`：硬门禁为零，主要指标达到阈值，未证明范围可接受，形成新基线；
- `rejected`：保留失败证据和根因，回滚候选，不美化为“部分完成”；
- `monitored`：持续接收真实 Bad Case、成本和恢复指标；
- `superseded`：由更新版本取代，历史报告和评测仍可追溯。

### 19.1 Definition of Ready

进入实现前必须具备：

1. 一个真实风险、Bad Case 或指标，不以“想加某技术”为理由；
2. 当前调用链、源代码位置、持久化边界和已有测试证据；
3. 本次唯一主要变量及明确不改范围；
4. 输入、输出、状态、权限、失败、预算和版本契约；
5. 正常、边界、安全、并发、恢复和对抗 Case；
6. 真实验证环境、证据保存位置和回滚方式；
7. 用户与模型的代码责任分配。

任一项缺失，状态保持 `proposed`，先补设计，不通过堆代码制造进度感。

当前 readiness 结论：路线图结构修订完成后，**P0-0 可进入设计确认，但任何生产代码包仍未 ready**。直接阻塞项是 pytest 环境不可用、当前差异未分类、当前主链没有可追溯 baseline Observation。先完成这些证据，不先写 TaskSpec 或改状态表。

### 19.2 固定实施流程

1. **冻结基线**：记录 HEAD、工作区候选、依赖、数据、模型、配置、测试命令和结果；
2. **写决策记录**：问题、约束、候选方案、取舍、不变量、失败语义、迁移和回滚；
3. **先定契约与测试**：先写 Schema、错误码、状态转换表和关键失败测试，再实现；
4. **做最小完整改动**：跨必要层完成一条真实主链，不留下可绕过的旧路径；
5. **分层验证**：静态检查 -> 单元 -> 契约 -> 集成 -> 真实依赖 E2E；
6. **主动故障注入**：超时、断连、重复、乱序、撤权、取消、旧 Worker、坏模型输出和脏数据；
7. **运行开发集评测**：定位 Bad Case，只改一个主要变量；基础设施包至少运行相关可靠性/安全集和全链 smoke，语义包运行完整业务开发集；
8. **运行冻结留出集**：候选不能针对留出集调参；语义/检索/模型候选必须比较完整业务留出集，纯确定性基础设施候选至少比较安全、恢复、主链非退化、P95 和成本；
9. **作候选决策**：adopt/reject/continue，写明证据、风险、未证明范围和回滚；
10. **运行反馈闭环**：新 Bad Case 脱敏入库，复现、归因、补回归、重新评测并版本化。

### 19.3 每包证据包

每个工作包固定保存：

1. `baseline_manifest`：代码、数据、模型、Prompt、工具、Schema、指标和评测版本；
2. `decision_record`：设计选择、替代方案、不变量和回滚；
3. `contract_and_migration`：Schema、数据库迁移、兼容策略和错误码；
4. `verification_manifest`：命令、时间、环境、退出码和产物 hash；
5. `fault_injection_report`：故障、预期、实际、恢复时间、数据一致性；
6. `evaluation_report`：开发/留出指标、硬门禁、P95、Token、成本和 Bad Case；
7. `candidate_decision`：晋升、拒绝或继续实验及未证明范围；
8. `rollback_proof`：代码、配置、数据结构和运行任务如何安全回退。

按风险选择验证 profile，而不是一刀切：

| Profile | 适用包 | 不可缺少的证据 |
|---|---|---|
| security | 权限、范围、隐私 | 跨租户/撤权/注入/删除传播硬门禁为零 |
| reliability | 状态、Outbox、恢复、Runtime | 并发、重复、乱序、崩溃、迟到、预算和恢复演练 |
| deterministic-domain | SQL、指标、计算、发布门禁 | 契约 Case、属性/边界测试、可复算血缘、全链 smoke |
| semantic | Planner、RAG、Claim、Prompt/Model | 开发集、人工校准、冻结留出集、Bad Case、质量/成本/延迟 |

一个 Work Package 可以同时属于多个 profile；所有命中的门禁取并集，不做平均分。

### 19.4 教学责任与完成声明

- 用户先负责高学习价值部分：不变量、契约、状态/权限/失败表、关键测试和至少一个核心实现；
- 模型负责审查漏洞、解释真实调用链、比较替代方案、补机械样板、组织验证和协助排错；
- 若用户明确要求模型完整实现，模型可以实现，但必须保留设计说明、验证边界和一项用户独立迁移练习；
- 系统门禁和学习门禁分别记录。项目代码达到候选条件但用户尚未独立完成时，不否认工程证据；但整个“教会你完成生产化改造”的阶段仍未完成；
- 测试通过只证明被测行为；没有真实依赖、故障注入、留出集和长期运行证据时，不宣称生产成熟。

系统门禁与学习门禁是 AND 关系；任何一个未通过，都不能宣称整个阶段完成。

---

## 20. 暂缓项与非目标

在核心正确性和评测闭环前暂缓：

- 更多 Agent 角色或自由协作框架；
- 微服务拆分；
- Kubernetes、服务网格、多区域；
- 复杂前端大屏；
- 为“通用性”建立大量抽象；
- 无业务指标支撑的模型升级；
- 没有真实 Case 前的大规模性能优化。

引入任何一项前必须回答：当前哪个可测量问题无法由现有最小架构解决？如何独立验证收益？失败时如何回滚？

---

## 21. 完成定义

“无限接近生产级”不是代码量、Agent 数或测试数，而是同时具备：

- 文本、文件、图片输入经过隔离、标准化、版本化和 provenance 管理，非法或不可信内容不能绕过控制面；
- 意图、参数、上下文、记忆、路由、计划和工具选择各有结构契约、停止条件和失败语义；
- 核心领域契约和状态迁移已实现并测试；
- 权限不能被 Prompt、上下文、客户端参数或旧 Worker 绕过；
- 核心数字可复算，事实有完整血缘；
- Claim–Evidence 支持关系可验证，证据不足会诚实降级；
- 重复、崩溃、超时、取消、撤权和版本变化都有确定行为；
- 真实 Worker E2E 能生成可审计 Observation；
- trace 能关联请求、计划、模型、工具、证据、状态、耗时、Token、成本和最终结果，并通过脱敏检查；
- 评测覆盖正常、边界、安全、恢复和对抗 Case；
- 硬门禁为零，冻结留出集无不可接受退化；
- 受控 HITL、数据生命周期、Kill Switch、故障隔离、备份恢复和回滚经过演练；
- 在明确的单节点容量、并发、P95 和成本预算内运行，超限时有背压或可操作终态；
- 基线、候选、Bad Case、成本和回滚证据完整；
- 用户至少独立完成一个跨层生产机制（优先状态/权限/恢复/评测）和一个业务证据切片的“设计 -> 实现 -> 验证 -> 排错”闭环；只完成一道指标题不足以证明工程化能力。

满足这些条件后，可以诚实描述为“单节点、生产风格、可审计的企业经营分析 AI 应用”。没有真实容量、高可用和长期运行证据前，不扩大为“已验证企业级生产系统”。

---

## 22. 参考清单覆盖与裁剪矩阵

此表用于审计参考资料是否真正进入本项目设计，而不是机械复制通用 Agent 功能。

| 参考能力组 | 本项目落点 | 验收证据 | 当前决策 |
|---|---|---|---|
| 输入、身份、Session、重复与非法输入 | 5.1–5.2、6.1、6.12 | API 契约测试、幂等冲突测试、截断元数据 | 必做 |
| 意图、实体、参数来源、澄清、改任务 | 6.3、6.12 | Intent/slot provenance Case、澄清/派生任务状态测试 | 必做 |
| Context、Working/Conversation/长期 Memory | 12.2 | 长上下文、冲突记忆、删除/TTL、权限测试 | 必做且有界 |
| Router、Planner、任务拆解、Workflow | 3.2、5.4、6.4、9 | 结构契约、有限路线、停止与状态迁移测试 | 必做 |
| Tool、参数/结果 Adapter、选择与权限 | 4、6、7、8、12.3 | Tool Schema、错误码、范围、超时和预算测试 | 必做 |
| Retry、Fallback、Circuit Breaker、Timeout | 9.4–9.7、12.3–12.4 | 故障注入、预算不重置、停止条件 | 必做 |
| 输出、Structured Output、Validation、自修复 | 6.10–6.12、11 | Schema、Claim Support、Publish Gate、repair Case | 必做 |
| 持久化、事务、幂等、取消、并发 Session | 5、9、12.4 | 原子性、重复投递、乐观锁、迟到写入测试 | 必做 |
| 权限、安全、隐私、Prompt Injection、HITL | 8、10、11.2 | 跨公司、撤权、注入、删除传播、审核审计 | 必做 |
| 日志、Tracing、Metrics、成本 | 12、13 | 完整关联链、脱敏检查、预算/P95/成本记录 | 必做 |
| Eval、Regression、Prompt/Model/Tool 版本 | 14、15 | 真实 Observation、冻结留出集、候选决策 | 必做 |
| Rate Limit、Cache、Kill Switch | 12.4 | 限流绕过、缓存隔离、禁用传播测试 | 必做 |
| 文本、文件与图片输入 | 3.4、5.1、6.1、P0-IN | 隔离/扫描/MIME/大小/OCR/版本/provenance/注入测试 | 必做；音频暂不做 |
| 写工具确认、Saga、补偿事务 | 3.1、3.4 | 只有引入外部写操作时重新设计 | 当前不适用 |
| 多 Agent 自由协作 | 3.3–3.4 | 必须优于当前受控 Workflow 的冻结评测 | 暂不做 |
| Kubernetes、多区域、微服务 | 1、16 阶段 10、20 | 单节点容量/可用性先出现明确不足 | 非当前主线 |
