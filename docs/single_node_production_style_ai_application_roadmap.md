# 企业经营洞察助手：全项目生产级设计与工程改造路线图

> 2026-10-07 最终范围更新：用户要求交付目标扩展到“具备真实上线条件的系统”。本文的单节点本地验证作为中间里程碑继续执行；完整上线架构、部署画像、P8–P10、灰度及 Go/No-Go 门禁见 [Agent 架构重构需求说明第 18 节](agent_architecture_refactor_requirements.md#18-最终上线蓝图与完整交付计划2026-10-07-新增)。按用户新要求，P5 须完成一个现有只读业务能力的受控 MCP 适配与本地等价验证；新增其他外部工具仍按需准入。下文早期“MCP 条件引入”以本条修订为准。本补充不代表当前代码或本机证据已达到上线条件。

> 最新执行约束：本文件保留最终设计范围；本期目标、阶段及退出标准以 [Agent核心优先执行计划](agent_core_first_execution_plan.md) 为准。全文旧M编号及“本期必做”是被重排的设计来源，不再作为核心学习前置要求；上传无独立里程碑，企业完备要求在第5层。

> 本文档是项目唯一主路线图，也是架构约束、阶段顺序和验收证据的最高项目规则。
> 目标是在单节点可验证环境中，建设一个可测量、可比较、可恢复、可解释、可审计的企业经营分析 AI 应用。
> 当前交付目标：现有 Agent 各模块的生产级设计与工程实现；评估 + 追踪 + 权限 + 回滚 + 成本贯穿所有模块。单电脑与存储服务完成本地真实验证，不要求公网部署。
> 最终范围：全项目模块改造与五项治理能力统一验收。第 0.3–0.5、16、18.1、21 节共同约束实施；分阶段不缩减最终范围。

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

以上为早期计划审计记录，不是当前进度。2026-09-15 已重新验证测试环境；当前事实与执行顺序见下文，不能继续以历史环境故障阻塞实施。

允许删除或重构旧设计、契约和兼容层，但每次必须同时写出受保护不变量、失败行为、数据/API 迁移、验证证据、回滚路径和未证明边界。缺任一项不得以“更生产级”为名开始重写。

---

## 0.1 当前交付范围与裁剪规则（2026-09-15）

目标是有生产级设计依据和本地工程证据的只读经营分析 Agent。不上线不等于只写设计：真实数据库、Worker、模型、检索、权限与恢复仍需跑通；不要求公网域名、云服务器、7×24 值守或高可用 SLA。

五项核心是一套闭环：真实任务 -> trace/证据/成本 -> 评测 -> 候选决策 -> 采用或回滚。权限和确定性正确性是不可折抵的硬门禁。

- **本期必做**：只读 SQL + RAG + 证据报告主链；真实结果评估；关联追踪与脱敏；任务范围与动态撤权；幂等/fencing/恢复；版本回退与备份恢复；预算、费用核算和本机容量说明。
- **按需扩展**：新增图片/OCR/更多格式、新的自动多模型回退、新缓存、复杂人工审核界面、完整 legal hold/隐私导出平台。它们是新增产品范围的选择，不豁免现有模块的完整工程改造。已纳入主线的输入、记忆、审批等能力均须按整体目标验收。
- **不可借裁剪绕过安全**：附件未达到 ready、范围不可信或最终发布未验证时必须拒绝；缺安全闭环的候选可以隔离或关闭入口，不能开放后标为“以后修复”。已完成附件候选保留，不自动删除。
- **保持不变**：受控自由 SQL、独立只读经营库、Schema Snapshot、RLS/公司范围、Outbox、租约、Checkpoint、结果边界与确定性发布权。不以固定查询替代 Agent 核心。
- **资源边界**：本机约 15.8 GiB RAM、16 逻辑处理器（本轮读取）；初始分析并发 1，评测串行，按需启用扫描/OCR/额外演示库。先测资源峰值，再决定是否并发 2；这不是已测容量。
- **存储边界**：外部存储用于原件、版本化证据包和备份；记录校验和、对象版本/不可覆盖 key、保留和访问控制。实际服务的版本化、耐久性和删除能力需单独验证，不默认已经具备。

现有模块及已经纳入主线的能力都须完成生产级改造，包含上下文、工作/会话/长期记忆、输入、Agent 节点、工具、SQL、RAG、发布与运行控制。阶段顺序只决定先后，不缩减最终验收范围。临时关闭不安全入口是止血措施，不算该模块改造完成；新增且无业务需要的能力仍可不引入。

本轮进度、代码证据及验证限制见 [2026-09-15 项目审计](project_core_audit_20260915.md)。系统工程验收与用户独立能力验收分别记录，不能相互冒充。

---

## 0.2 Agent 底座的改造判断（2026-09-15）

五核心建立在业务 Agent 底座上，不能只加审计表而忽略上下文、工具和证据正确性。详细代码依据、调用链与验收 Case 见 [当前审计第 4 节](project_core_audit_20260915.md#4-agent-基础设计逐项判断)。

| 模块 | 决策 | 最小必要改造 | 对应阶段 |
|---|---|---|---|
| 架构/模块 | 保留模块化单体与 LangGraph 受控工作流 | 分开持久化 State DTO 和运行 context；补版本兼容；不拆微服务 | M1/M2 |
| Planner/Data/Knowledge/Reviewer | 保留角色、收紧决定权 | 结构化输入输出、参数来源、有限重试；语义复核不能取代确定性权限/发布 | M1–M3 |
| 上下文 | 局部重构为统一有界构建 | 来源、选择 manifest、完整输入 Token 与输出预留；修首条 RAG 超限 | M1/M2 |
| 工作/会话记忆 | 保留 | 版本、来源、范围与当前问题优先；恢复不能加载不兼容状态 | M1/M2 |
| 已有长期报告记忆 | 必须完成治理改造 | 写入/读取/冲突/失效/删除/版本/预算/评测全生命周期；历史数字重新取证 | M1 契约与隔离、M3 质量、M4 生命周期演练 |
| ToolRuntime | 保留并作为唯一执行边界 | 每工具 Schema、服务端授权注入、结果上限、Deadline、总预算、审计 | M0–M2 |
| MCP | P5 完成一个现有只读业务能力的受控适配；其他外部工具按需 | 复用 Runtime，固定可信来源、工具版本、权限和数据外发边界；本地/MCP 等价验证 | P5，更多外部工具有明确需求再做 |
| Skill | 条件引入 | 多种真实流程复用时做版本化流程包，不执行用户脚本、不授予权限 | M3 后有明确需求再做 |
| RAG | 保留 pgvector 与现有检索/重排 | 空范围拒绝、当前 ACL、不可变证据、支持/冲突/不足判断；检索与回答分别评测 | M0/M1/M3 |
| SQL | 保留受控自由生成，强化校验计算 | 指标/时间口径、AST 范围/列/Join/函数/硬 LIMIT、结果类型、Decimal 计算与血缘 | M1–M3 |

MCP 是接入协议，Skill 是可复用流程知识，Tool 是执行接口；三者均不是权限或发布的决定者。现有业务 backend 未发现 MCP/Skill 运行时接入，不以开发工具支持替代产品实现证明。

---

## 0.3 全模块生产级改造要求（用户澄清后修订）

目标是提升现有各模块的设计和实现标准，五项核心是横向验收维度，不是只改五个模块。保留某组件/框架不等于保留其不合格的契约或实现。现有设计不满足要求时，可以替换内部设计，并给出迁移、回滚和证据；不能只补文档、日志或把功能关掉后宣布完成。

### 全模块共同门禁

每个模块须明确：职责与不变量；结构化输入输出及版本；状态、权限与数据归属；超时、预算和失败语义；可观测事件与证据；迁移、恢复和回滚；测试、真实依赖验证和未证明范围。标为不适用的项须给出具体理由。一个模块通过单测而缺少其关键集成/故障证据，只能标记部分验证。

### 上下文目标设计

调用链：冻结任务 + 当前授权 + 当前问题 -> Context Builder -> ContextManifest + 有界模型输入 -> Gateway 复核完整输入和输出预留 -> 持久化选择记录。

- 分类装载系统规则、当前问题、冻结范围、会话历史、记忆和证据；不可信内容不能改变规则与权限。
- 每个片段关联来源 ID/hash/版本、业务时间、可信度、用途、Token 计量和选入/舍弃原因；摘要必须保留来源，不把模型摘要当权威事实。
- 完整输入预算覆盖系统 Prompt、工具描述、历史、记忆、证据及协议开销，并预留最大输出；上限约束覆盖首条证据和失败重试。
- 关键时间/实体/否定条件不能被静默截断；无法安全容纳时缩小证据、要求澄清或稳定失败。
- 快照复现仍受当前授权否决；复现指相同版本与选择过程可审计，不承诺远程模型逐字相同。
- 验收：长短历史、跨主题、指代、冲突、恶意历史、关键字段截断、Token 超限、版本重放、撤权；比较任务质量、错误补全率、Token 和时延。

### 记忆目标设计

调用链：已验证报告 -> Memory Candidate -> 写入策略与来源检查 -> 版本化记忆 -> 当前授权/有效期/相关性选择 -> Context Builder；撤回/纠错/删除事件必须传播到后续读取和派生内容。

- 工作记忆保存执行状态并受 Checkpoint 版本与执行权保护；会话记忆用于指代与连续交互；长期记忆保存有来源和明确适用范围的历史信息。
- 写入绑定 company/user、来源任务/报告/证据版本、内容类型、适用业务时间、失效条件、策略版本和幂等键；禁止把假设或未经证明的数字写为确定事实。
- 读取同时检查当前授权、来源可用性、时效与当前问题相关性，再进行 Token 限额选择；有记忆不代表必须使用。
- 冲突记录分别保留版本和适用时间，不能自动采用最新一句话；无法消解时明确缺口。记忆只帮助规划，当前业务数字与归因重新取证。
- 纠错/撤回/删除可追溯，传播到派生记忆和后续上下文；备份恢复不得重新激活已撤回内容。正文保留与最小审计分离。
- 旧记忆不能可信回填来源时标为不可验证并停止自动使用，保留迁移记录；新机制须实际恢复受控记忆能力后才能验收。
- 验收：幂等写入、撤权/过期、来源删除、冲突、错误事实污染、跨租户、注入、恢复后失效仍生效；用无记忆/有记忆对照衡量收益与费用，不以命中率单独证明价值。

阶段落点：M1 完成上述契约、授权、来源和版本；M2 完成预算与异常控制；M3 完成上下文/记忆与 SQL/RAG 的真实质量评测；M4 完成迁移、删除与恢复演练；M5 对全部模块逐项验收。后续教学一次只实施一个可解释切片，不一次替用户重写全项目。

---

## 0.4 全项目统一改造矩阵与总验收

用户要求的是整体改造：纵向各模块的生产级设计与横向评估、追踪、权限、回滚、成本共同构成一个交付目标。不得将前者当作可选增强，也不得只完成横向治理后宣布项目完成。第 0.1 节按需项仅指新增且尚未纳入产品的能力，不包括现有模块的必要工程治理。

| 模块域 | 必须完成的目标设计与工程改造 | 主要阶段 |
|---|---|---|
| API、身份、公司、会话 | 服务端身份与范围、唯一幂等、输入契约、原子任务创建、稳定错误与取消/重跑语义 | M0/M1 |
| 输入与附件摄取 | 已支持格式的隔离/扫描/解析、不可变版本、资源上限、状态与失败恢复、出处和删除；当前冻结 | 新第4层D1，无独立里程碑 |
| 上下文 | 来源/可信度分层、关键参数保护、统一 Token 预算、选择记录、截断/摘要验证与复现 | M1/M2/M3 |
| 工作、会话、长期记忆 | 来源与写入门禁、版本/时效/冲突、当前授权、相关性选择、失效/删除传播与恢复 | M1/M3/M4 |
| Planner、Agent 节点、Router | 结构化意图/计划/节点结果、受控路由、明确停止条件、总重试预算与错误传播 | M1/M2/M3 |
| 工具与模型运行时 | 唯一执行入口、Schema、服务端权限、供应商适配、版本、超时、预算、失败与降级策略 | M0/M1/M2 |
| SQL、指标、计算 | 受控自由 SQL、只读和范围约束、指标/时间口径、结果类型、硬资源上限、可重算数字与血缘 | M1/M2/M3 |
| RAG、文档、向量索引 | 授权前置、不可变证据、摄取/索引一致性、检索与答案分开评估、冲突/不足/时效 | M0/M1/M3/M4 |
| 报告、Reviewer、审批 | Claim 与证据、确定性校验、草稿版本绑定、当前授权、唯一发布与可解释拒绝 | M1/M3/M4 |
| 任务、Outbox、Worker、Checkpoint | 状态与业务结果分离、原子认领、心跳/fencing、交付对账、兼容恢复、取消/迟到处理 | M1/M2/M4 |
| 数据、存储、配置与版本 | 迁移、保留/删除、备份一致性、秘密管理、运行版本冻结、候选切换与回退 | M1/M4/M5 |
| 评估、追踪、审计与成本 | 真实 Observation、分层评测、关联事件、脱敏、硬门禁、完整调用账本与可信费用状态 | M0 起贯穿全部阶段 |
| 本机运行与交付 | 干净重建、真实依赖 readiness、低并发容量、背压、故障演练、运维步骤与独立演示 | 逐阶段验证，M5 总验收 |

每行都按五个横向维度记录证据：

- **评估**：契约/故障 Case；涉及模型语义时有业务质量对照；缺证据不记通过。
- **追踪**：谁以哪个任务/执行/配置/输入版本触发，产生何种结果及失败。
- **权限**：该模块的数据、动作及其派生结果是否始终受当前授权与冻结范围约束。
- **回滚**：版本或状态改变失败时，如何恢复兼容状态、停止或派生重跑；不会撤销的事实明确保留。
- **成本**：涉及模型时核算调用/Token/费用，其他模块核算时间、CPU/内存、结果大小、存储等相关资源；不生造无意义的模块美元价格。

所有模块采用同一进度记录：目标设计明确 -> 契约/失败场景明确 -> 候选实现 -> 模块验证 -> 真实集成/故障验证 -> 全链非退化 -> 采用。当前源码已满足的部分按证据复用，不为“整体”而重写正确代码；不满足的内部设计允许替换，须携带迁移和回滚。

M0–M4 是交付切片，不是范围删减。M5 必须逐行检查本矩阵：有未通过模块时，只能报告阶段进展，不能宣布整体生产级改造完成。用户已明确要求 P5 完成一个受控业务 MCP 适配；更多外部 MCP 工具及 Skill 是否引入仍由实际业务接入/流程复用需求决定，有需求且纳入后同样接受全部门禁。

单机限制只裁剪高可用、多区域、线上流量和公网交付等证明范围，不裁剪模块正确性、授权、失败恢复、可观测性和资源控制要求。不上线的完成声明必须明确为本地生产级工程验证，不冒充线上生产成熟度。

---

## 0.5 生产级要求复审与强制验收补充（2026-09-15）

### 复审结论与证据声明

此前版本覆盖面基本完整，但对授权竞态、审计失败、预算崩溃对账、删除后恢复、供应链、外部数据发送与服务目标的要求不够具体，因此不能仅凭原计划宣称模块或治理达到生产级。本节补充是强制实施约束，不是可选增强。

统一目标是“符合明确适用范围的生产级设计与工程要求，并完成单节点真实验证”。生产级不是一份统一的 Agent 认证或名词清单；本项目采用具体风险、约束、契约、测试与运行证据验收。计划通过代表实施依据可用，不代表代码已合格。未上线意味着真实用户流量、持续可用性及长期运营仍未证明，而不是降低应用工程要求。

### 治理贯穿全链时必须成立的细则

| 领域 | 必须落地的机制和失败行为 | 必须提供的验证 |
|---|---|---|
| 授权竞态 | 冻结许可与当前授权取交集；授权变更和调用准入/发布定义事务顺序与 auth epoch。撤权提交后不得准入新调用或发布；已在撤权前准入的外部调用可能无法召回，记录在途边界并拒绝其结果进入后续业务使用 | 双连接屏障制造检查/撤权/调用/发布交错；连接池租户上下文清理；禁止只靠测试前后串行撤权 |
| 只读与隔离 | API、Worker、检索、导出、记忆、报告读取均按资源授权；数据库应用角色不得拥有 superuser/BYPASSRLS，表所有者与应用角色分离；受控查询限制危险函数、系统目录及外部连接 | 分别用实际应用角色验证 RLS 与只读；跨用户/公司/行列/文档/派生内容反例；不只用管理员连接跑通过测试 |
| 原子副作用 | 发布、任务终态、消息与关键发布审计同事务；报告有唯一约束和执行权检查。Outbox 至少一次交付与业务去重分开，不承诺外部模型调用 exactly-once | 在事务提交前后、Broker 确认前后、模型响应前后杀进程；重复消息只有一个可见报告，所有可能付费调用保留账目 |
| 审计失效 | 授权准入、预算预留、发布等关键审计持久化失败时禁止对应动作；普通遥测导出故障允许有界缓冲和告警，不允许无限占内存或默默丢关键记录。调用审计使用唯一 ID，不只依赖 max(sequence)+1 | 注入数据库写失败、遥测后端断开、缓冲溢出、并发事件；证明业务事务与关键审计一致 |
| 成本结算 | 调用前持久化 call_id、预留量与 execution；账本有 reserved/settled/unknown。模型、Embedding、重排、OCR、扫描及存储分别标明收费或资源口径；SDK 隐式重试必须计入或禁用 | 预留后崩溃、收到响应后未结算、超时后迟到费用、重复结算、跨 attempt 并发；unknown 不退款、不计零，供应商可查则对账，不可查则保守封账 |
| 取消后账目 | 取消/旧 Worker 不得更新业务结果，但已发生调用的结算/拒绝审计允许按 call_id 幂等追加；不得因此清空取消状态或重启执行 | 取消与响应同时到达、恢复旧执行后迟到结算；任务不复活且账本不漏计/双计 |
| 数据外发与输出 | 发给模型的数据先经过分类、字段最小化及允许的供应商策略；不允许模型决定目的地址。报告展示转义不可信 HTML/链接，导出与下载执行授权；附件解析进程限制网络、CPU/内存/时间与可访问目录 | 敏感字段诱导、外部 URL/私网访问、恶意 HTML/Markdown、CSV 公式注入、解析器超限；验证拒绝/降级与审计 |
| 索引与生命周期 | 文档发布在内容/解析/chunk/index 版本一致后才 ready；失败摄取不能切换可见索引；删除/撤回有 tombstone 与处理水位 | 摄取中断、重复处理、索引半更新、重建、删除；SQL/RAG/记忆/报告均不能混用不同资源版本 |
| 恢复后的权限与删除 | 恢复快照后，先重放截至允许服务时点的授权/撤回/删除记录并校验水位，再开放读取；相关记录须独立于旧快照保存。水位未知或对象 hash 不符则保持不可用 | 在备份之后撤权/删除，再恢复旧备份；旧内容仍不可读；记录数据库、对象与删除日志的实际恢复点 |
| 供应链与秘密 | 依赖/镜像/模型与解析器版本可重建；记录漏洞审查与处置，阻断适用的未缓解严重漏洞；Secret 最小权限、轮换与泄露响应可执行；MCP/Skill 启用时固定可信来源/版本 | 干净构建、依赖与镜像扫描、秘密扫描、凭据轮换、旧凭据失效、工具/Skill 内容变化拒绝未批准版本 |
| 运行控制 | 单用户/公司及全局请求、队列长度、并发、连接池、磁盘、对象大小和日志保留都有上限；依赖故障有超时/背压/隔离；存活检查不等于就绪检查 | 队列洪峰、模型 429、DB/Redis/存储断开、磁盘不足、时钟偏差与长调用；安全停止/恢复，不能无限排队或重试 |

以上属于本项目的设计要求。Prompt Injection 的目标是约束攻击影响、阻止越权和无证据发布，不承诺所有攻击都能被文本过滤器识别。语义真实性依赖 Gold、人工校准、拒答/降级和持续评测，不冒充确定性数学证明。

### 指标契约与禁止事后降标

每个工作包在 ready 时写明：指标定义、分子/分母、适用 Case、样本/重复数、环境、阈值、超限动作、证据路径与负责人；验收时不得留 TBD。性能和语义阈值允许由先行基线测量确定，但必须在候选实现/留出评测前冻结，不能看到候选结果后下调。无真实基线时可以实施测量工具或安全修复，不得宣称效果优化成功。

- 所有适用安全/确定性正确性反例零违规；unknown/缺审计/缺范围证明不计通过；零违规只指声明测试集，不代表未知攻击不存在。
- 所有声明支持的状态转换、并发/故障反例必须通过；每次验收模型/工具调用及发布/拒绝均有完整关联与结算状态。
- 业务质量按问题类型报告成功率、数值正确性、支持正确性、拒答/不足状态准确性；正常回答和安全拒绝使用不同期望，不能要求取消或拒绝任务也必须持久化报告。
- 开发/留出严格分离；语义 Judge 与被测 Agent 不共享答案，Judge 对人工标注校准；报告样本量、重复运行波动及适当置信区间，不用几十例百分比冒充总体保证。
- 服务目标明确成功率、队列等待、任务/节点 P95、超时与资源上限；恢复目标明确 RTO（恢复服务最长目标时间）与 RPO（允许丢失的数据时间窗口）。在 M1 设计初值，M2 首轮故障/容量基线后冻结，M4/M5 实测验收；不能只在演练后记录耗时而没有事先目标。
- 成本报告含全部尝试、失败与拒绝调用的总费用/估计/unknown、每可信成功任务费用、资源峰值；单任务和单次评测运行总预算均受控。

### 阶段依赖与既有目标对齐

- M0：真实测量闭环与紧急范围修复；不等待全域重构。
- 上传：当前冻结，完整摄取闭环改为新第4层D1，不前置于Agent核心。
- M1：任务/资源/授权/上下文/记忆契约、审计 Schema、数据分类与保留、RTO/RPO 初值、迁移策略；版本身份先于可靠重放。
- M2：基于 M1 实现并发授权、调用账本、心跳/Deadline/对账、背压、关键审计失效处理；用真实事务与杀进程验证，不能等 M4 才第一次测故障。
- M3：在以上边界内改进完整 Agent/上下文/记忆/SQL/RAG/报告质量；数据集修正与指标口径、审核机制一并进入业务 Case。
- M4：全模块版本回退、备份/删除/授权恢复、事故处置；M1 的生命周期设计在此完整演练，不是到这里才定义。
- M5：全矩阵回归、干净重建、容量和运行观察；任何必须项没有证据，整体不通过。

设计账本的已确认能力必须有落点，不因漏写阶段而被静默删除：DatasetMapping/Normalization 与 DataQualityReport 在 M1 定契约、M3 实现验证、M4 演练；角色/直接授权及双边跨公司审批在 M1 明确范围、M2 验证竞态、M3 验证业务；独立审核与草稿 hash 在 M1/M3/M4 验证；认证选择一种适合本项目的完整方案，SSO/OIDC/SAML 是替代接入选项，不要求堆三套协议，令牌撤销、有效期、高风险操作再认证与审计必须验证。

跨公司目标仅允许服务器持有双方批准且未过期/撤销的明确资源授权；“跨公司硬门禁为零”指未经授权的跨公司读取。当前普通任务保持单 active company。跨公司分析须使用显式授权任务和逐数据源隔离的上下文，不关闭 RLS 或扩大普通工具范围；未实现前明确拒绝，不伪称现有支持。

### 参考依据与采用边界

- [OWASP Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)：支持不可信输入隔离、最小权限和对抗测试；不能据此声称注入绝对消除。
- [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)：用于约束工具能力、权限和自主动作范围。
- [Google SRE 服务目标](https://sre.google/sre-book/service-level-objectives/)：用于指标/目标的定义与先行约定，不提供本项目可直接照抄的 SLA 数值。
- [PostgreSQL 16 RLS](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)：据实际角色验证策略；超级用户、BYPASSRLS 与表所有者边界必须核对。

这些参考用于设计审查，不是认证或“生产级已达标”的证明。

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

- 具备生产级的单节点系统设计；
- 具备严格权限、证据、状态恢复、评测和审计闭环；
- 适合受控内测、低并发试运行或作为进一步生产化的可靠基线。

不能仅凭本路线图宣称：

- 多节点高可用、跨区域容灾或明确 SLA；
- 已承受真实企业规模流量；
- 任意业务问题都能正确回答；
- 测试通过等于真实业务 E2E；
- RAG Recall 提升等于最终报告质量提升。

---

## 2. 当前实现与验证进度

当前实现事实与验证范围统一记录在 [项目审计](project_core_audit_20260915.md)，本路线图只维护目标、实施顺序和验收要求。历史环境故障、测试数量及早期候选状态已从本节移除，避免与当前事实混淆。后续进度更新必须附代码版本、候选差异与验证证据。

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
| 运维控制 | 配置分层、readiness、告警、隔离/死信、备份恢复、回滚、灰度和 Kill Switch | P0-C、P0-G、P1-B、P1-C、M4/M5 |

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
- 安全与正确性硬门禁不得被普通配置或紧急例外关闭；紧急操作仅允许停用、缩小范围或回退到仍满足门禁的版本，并须审计；
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

- 未经授权的跨公司或任务范围外数据；
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

## 16. 当前实施顺序：Agent 核心优先

按用户 2026-09-15 最新要求，唯一执行顺序改为 [Agent 核心优先执行计划](agent_core_first_execution_plan.md)：第1层度量 → 第2层Agent核心 → 第3层治理 → 第4层基础设施 → 第5层企业完备演进。旧 M0–M5 编号只用于历史映射，取消 M1-IN 独立里程碑。

本期目标是可面试讲清楚并提供运行证据。上传冻结；已有 RLS、Outbox、Fencing 保留，其强化不能阻塞核心学习。第0.1–0.5、18–22节保留最终设计范围，不能作为第1–3层全域前置门禁。各层退出按新计划；本期验收不代表第21节全部工程要求已完成。

---

## 17. 实现位置与修改定位

当前代码按领域组织于 `backend/app/modules/`。目录与跨模块边界见 [模块化单体目录约束](modular_monolith_structure.md)，模块事实及具体问题见 [项目审计](project_core_audit_20260915.md#4-agent-基础设计逐项判断)。修改前沿当前调用链核对源码、测试和差异；不再使用旧 `services/`、`models/` 平铺目录地图。

目标模块与阶段映射统一使用第 0.4 节，强制治理验收使用第 0.5 节，实施顺序统一使用第 16 节。

---

## 18. 当前实施程序与可复用设计契约

生产化的实施单位不是“做完一道销售分析题”，而是一个能贯穿真实主链、消除一个系统性风险、具备故障与回滚证据的 Work Package。业务问题只是验收数据，不能决定系统边界。

每个 Work Package 不要求机械修改所有层；它必须列出受影响与不受影响的边界，并沿受影响链追踪 API/服务端事实/持久化/异步/工具/权限/终态/审计。完成证据至少包括本包契约与故障测试，以及整条主链非退化 smoke。只新增一个 Pydantic 类、Prompt、Agent 节点或单元测试，不能独立算作生产化完成。

### 18.1 工作包与当前里程碑映射

原 P0/P1 与下表M编号仅保留历史契约映射；唯一执行顺序及当前映射见第16节链接的新五层计划。不得按旧表前置基础设施。

| 原工作包 | 当前落点 | 本期范围 |
|---|---|---|
| P0-0 | M0 | 现有环境复用、候选指纹、测量反例、真实 Observation |
| P0-IN | 新第1–3层冻结，新第4层D1实现验证 | 仅必要阻断/越权修补；完整上传工程与OCR验收后移 |
| P0-A0/A1/A2 | M0 权限止血、M1 契约与版本 | 不等待全状态重构才修权限 |
| P0-B/C | M2 故障控制、M4 演练 | fencing、预算不重置、对账、兼容恢复 |
| P0-D/E/F | M3 | 由真实错误驱动 SQL、计算、声明支持与唯一发布门禁 |
| P0-G | M0 计量、M2 控制 | 成本提前；多供应商自动回退按需 |
| P0-H | M0 开始、贯穿 M1–M5 | 不再等后期才接真实 Worker 评测 |
| P1-A | M1 上下文与记忆契约、M3 质量、M4 生命周期 | 工作/会话/长期记忆均需验收，不以关闭功能代替完成 |
| P1-B | M2 预算、M5 容量 | 缓存无实测收益则不加 |
| P1-C | 各包回滚计划、M4 演练 | 最小停机开关、事故复盘；完整审核产品按需 |
| P1-D | M1/M4 最小生命周期 | 已用资源的保留/删除/备份边界必做；完整合规平台不纳入 |

### 18.2 首个实施批次：P0-0 工程接管与基线

当前测试环境已可用。首批按 M0 修复测量契约和权限边界，并建立真实 Observation；只补当前切片缺少的证据，不重做历史大审计。下列产物可合并为一个 manifest 和一份报告，不要求为了格式创建多套台账。

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

### 18.4 P0-A 设计契约参考：状态、范围、资源版本与任务权威链

本节保留目标契约与历史风险说明，不是当前完整实现判断；实际缺口先按第 0.2 节和审计报告复核，再按 M0/M1 小切片推进。

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
10. 取消、撤权、Kill Switch 或旧执行迟到：停止后续业务动作，迟到业务结果拒绝；已发生调用的费用及拒绝审计按不可变 call_id 追加，不复活任务；
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

2026-09-15 readiness：测试环境可用，五核心闭环尚未验收。每个 M0 修复切片补齐自身契约、失败反例、验证和回滚即可进入实现；真实 Observation 是 M0 的交付目标，不应成为编写该 Adapter 或修复评测器的循环前置条件。

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

## 21. 全模块生产级改造完成定义

以下条件合取，工程证据不可用学习理解或测试数量替代：

1. 评估：真实 Worker 持久化结果进入 Observation；独立开发/留出集、人工 Gold、逐项硬门禁、候选比较与 Bad Case 可复现，unknown 不计通过。
2. 追踪：验收任务从请求到发布/拒绝、每次 attempt/模型/工具/证据/版本/费用可关联，脱敏测试通过。
3. 权限：跨公司、空范围、伪造范围、动态撤权、注入和迟到写入反例全拒绝；RLS/只读经营库与应用授权分别验证。
4. 回滚：候选版本回退、故障任务恢复、备份恢复三类演练有证据；状态、对象、引用与账本一致，记录恢复时间及丢失窗口。
5. 成本：每次调用含失败/重试都有计量状态；任务预算跨 attempt 生效，调用前预留、事后结算；unknown 不冒充零成本。报告总成本及每可信成功任务成本。
6. 业务底座：保留只读 SQL/RAG/报告主链，核心数字可复算、结论有证据，证据不足可诚实降级，发布依赖确定性门禁。
7. 本机验证：干净重建、真实依赖 E2E、有限并发资源/P95/成本测试与故障演练可重现；无需上线，不声称单机故障仍可用。
8. 学习证据：用户独立完成至少一个状态/权限/恢复/评测跨层机制和一个业务证据切片的设计 -> 实现 -> 验证 -> 排错；工程已完成但此项未完成时分别报告。

9. 全模块验收：第 0.3 节共同门禁、第 0.4 节逐模块矩阵、第 0.5 节治理细则和冻结指标全部完成，五项治理能力与模块工程结果共同验收；上下文与工作/会话/长期记忆必须完成生产级改造，不能用临时禁用代替验收。

新增格式、复杂审核界面、新缓存与完整合规平台不作为必然新增项；现有相关能力仍按共同门禁改造。目标名称为“单节点验证、未上线的生产级 Agent”，不使用无证据的“已验证企业级生产系统”。

---

## 22. 参考清单覆盖与裁剪矩阵

此表保留完整设计覆盖清单；“必做”须按第 0.1 节应用到本期已开放能力，不能覆盖 M0–M5 的裁剪。仅新增格式、完整合规平台及复杂审核界面为条件启用；现有记忆与其他模块的工程治理必做。

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
| Kubernetes、多区域、微服务 | 1、16 M4/M5、20 | 单节点容量/可用性先出现明确不足 | 非当前主线 |
