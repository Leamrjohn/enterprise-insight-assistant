# Enterprise Insight Assistant 后端产品与交付规划

> 文档性质：产品目标、后端架构、代码规划和交付验收的主要依据
> 当前基线日期：2026-07-20
> 适用项目：Enterprise Insight Assistant（企业经营洞察助手）

## 1. 文档目的

本文档回答以下问题：

1. 项目的最终目标是什么。
2. 最终产品必须具备哪些功能。
3. 当前代码已经做到什么。
4. 当前项目距离目标还缺少什么。
5. 后端应该采用什么架构。
6. 每个目录和文件应该承担什么职责。
7. 数据库、Schema、API、Worker 和 Agent 应该如何协作。
8. 应按什么顺序实现和验证。
9. 做到什么程度才能称为“真实可用”。

本文档描述的是后端产品交付主线。学习过程和教学规则由根目录 `AGENTS.md` 规定。

---

## 2. 项目最终目标

项目最终交付一个面向中小型公司经营人员的独立 Web 应用：

> 用户提出经营问题，系统从已授权的只读经营数据库和该用户的文档知识库中获取证据，生成包含事实、原因假设、建议、引用和限制的结构化经营分析报告。

第一版不是通用聊天机器人，也不是无限自主 Agent。

第一版必须能够可靠回答以下类型的问题：

1. 某区域销售额为什么下降。
2. 某类产品毛利为什么下降。
3. 某时间段客诉为什么上升。
4. 哪些客户存在应收风险。
5. 某项问题只有数据事实、但缺少原因文档时，明确说明证据不足。

项目不承诺自动发现唯一真实根因。系统输出的是：

- 数据确认的事实。
- 文档支持的原因假设。
- 与事实或假设关联的建议。
- 当前证据的限制。
- 可以继续采取的分析动作。

---

## 3. 产品要做到什么程度

最终目标不是大型企业级平台，而是“生产风格、可内部试用的中小型应用”。

### 3.1 必须达到

- 可以通过 Docker Compose 启动。
- 可以完成登录或可靠身份认证。
- 用户只能访问自己的文档、任务和报告。
- 可以上传并处理 TXT、Markdown、PDF。
- 可以从独立只读经营数据库查询数据。
- 用户不能提交原始 SQL。
- 可以异步执行较长分析任务。
- 可以查询进度、取消任务、查看失败原因。
- 可以生成结构化报告。
- 数字能追溯到查询结果。
- 文档引用能追溯到真实 chunk。
- 文档不足时返回 `partial`，不能编造原因。
- 数据或模型完全失败时返回 `failed`。
- Worker 重复收到任务时不会重复产生报告。
- 日志能够定位一次请求经过的任务、节点和失败阶段。
- 具备自动化测试和可重复评测数据。

### 3.2 暂时不要求

- Kubernetes。
- Terraform。
- 完整企业级多租户 SaaS。
- 实时 BI。
- 任意自然语言 SQL。
- 用户直接输入 SQL。
- 自动修改经营数据库。
- 自动执行经营决策。
- 多 Agent 自由辩论。
- OCR 和图片分析。
- 大规模分布式部署。
- 复杂计费、配额和控制平面。

---

## 4. 第一版业务范围

### 4.1 场景一：区域销售下降

示例问题：

> 华东区 2025 年 8 月销售额为什么比 7 月下降？

系统应执行：

1. 查询两个期间的区域销售额。
2. 计算变化额和变化率。
3. 下钻主要客户。
4. 找出造成下降的客户。
5. 检索合同、客户沟通、竞争情况等文档。
6. 区分数据事实和文档假设。
7. 生成跟进建议。

### 4.2 场景二：毛利下降

系统应执行：

1. 查询品类毛利和毛利率变化。
2. 下钻产品、成本和折扣。
3. 检索供应商涨价、促销或竞争文档。
4. 生成价格、采购和产品结构建议。

### 4.3 场景三：客诉上升

系统应执行：

1. 查询客诉数量、严重度和类别趋势。
2. 下钻产品、客户或供应商。
3. 检索质量报告和售后记录。
4. 给出排查、召回、供应商沟通等建议。

### 4.4 场景四：应收风险

系统应执行：

1. 查询未回款金额和账龄。
2. 下钻客户和发票。
3. 检索回款沟通和客户风险资料。
4. 给出分级催收和信用控制建议。
5. 不得把逾期直接描述为坏账。

---

## 5. 报告可信度契约

### 5.1 事实

事实必须：

- 来自受控查询结果。
- 包含数据证据 ID。
- 使用确定性代码计算数字。
- 不依赖 LLM 心算。
- 可以使用同一参数重新查询。

### 5.2 原因假设

原因假设必须：

- 关联至少一项已确认事实。
- 关联至少一个属于当前用户的文档 chunk。
- 标注为假设，而不是已证明因果。
- 文档不足时不生成确定原因。

### 5.3 建议

建议必须：

- 关联事实或假设。
- 包含优先级。
- 包含具体行动。
- 尽可能包含验证指标。
- 不允许自动执行经营动作。

### 5.4 限制

以下情况必须产生限制：

- 数据查询没有结果。
- 未检索到文档。
- 文档相关性不足。
- 数据和文档存在冲突。
- 模型调用失败。
- 引用或结构校验失败。
- 只能确认现象，不能确认原因。

---

## 6. 当前项目已经具备的能力

当前代码已经包含：

- FastAPI 应用入口和分层目录。
- PostgreSQL、SQLAlchemy、Alembic。
- 用户、文档和分析任务模型。
- API Key 认证和用户级资源隔离。
- 文档 CRUD 和文件上传。
- 文件类型、大小、空文件和 SHA256 校验。
- 文档异步解析、分块和 Embedding。
- pgvector 检索和用户过滤。
- Redis 和 Celery。
- 分析任务状态、阶段、取消和分类重试基础。
- Model Gateway。
- RAG Tool。
- SQL Tool、SQL AST 校验和业务语义目录。
- Planner、Data、Knowledge、Reviewer Agent。
- LangGraph 工作流。
- 可复现模拟经营数据。
- Docker Compose。
- 单元测试和集成测试。

这些代码证明项目已经有较完整的基础模块，但不证明最终业务链路已经完成。

---

## 7. 当前距离最终目标的主要差距

### P0：交付阻塞问题

#### 7.1 测试和静态检查没有全绿

当前验证结果：

- 128 个测试通过。
- 4 个测试失败。
- 2 个 E2E/慢速测试未执行。
- Ruff 有 1 个错误。

必须先恢复全绿基线。

#### 7.2 Worker 没有接入数据加文档工作流

当前 `/tasks` Worker 只执行 RAG。

LangGraph 中虽然存在 Data、Knowledge 和 Reviewer，但没有被 Worker 主链调用。

最终必须统一为：

```text
Analysis API
→ Celery Worker
→ Planner
→ Data Tool
→ Knowledge Tool
→ Report Builder
→ Deterministic Validators
→ Persist Report
```

#### 7.3 最终结果仍是旧 RAG Schema

当前结果主要是：

```json
{
  "answer": "...",
  "citations": [{"chunk_id": 1}]
}
```

最终必须改为结构化经营报告，包括：

- scenario
- confirmed_facts
- hypotheses
- recommendations
- data_evidence
- document_citations
- limitations

#### 7.4 固定查询模板尚未进入主链路

MVP 应使用固定 `query_id + parameters`。

当前 Data Agent 主要使用 LLM 生成 SQL，不符合固定场景优先的产品边界。

#### 7.5 查询注册表和 SQL 校验规则冲突

固定查询使用 CTE，但通用 SQL 校验器禁止 CTE。

应新增专门的 `TemplateQueryTool`：

- 只接收查询 ID 和参数。
- 只执行代码仓库内登记的 SQL。
- 不接收用户或 LLM 生成的 SQL。
- 使用参数化执行、只读事务、超时和行数限制。

#### 7.6 Planner 输出不完整

Planner 目前只决定是否查数据或文档。

最终 Planner 必须输出：

- 场景。
- 标准化问题。
- 查询计划。
- 区域和时间范围。
- 需要使用的查询 ID。
- 文档检索范围。
- 是否允许在缺少文档时输出 partial。

#### 7.7 缺少可靠的事实构建器

不能让 LLM 根据 SQL 行自由编写所有数字。

应由确定性代码把查询结果转换为：

- MetricComparison
- DataEvidence
- ConfirmedFact

LLM 主要负责解释、归纳和组织语言。

#### 7.8 校验器尚未真正接入

已经存在引用、数字、格式等校验代码，但还没有形成最终报告的统一校验链。

#### 7.9 认证和文档目标不一致

当前是 API Key，规划文档写 JWT。

应做出明确选择：

- MVP 前期保留 API Key，但安全存储哈希值；或
- 实现密码哈希、登录和 JWT。

未实现前，文档不能声称支持 JWT。

#### 7.10 Docker 经营数据库账号不完整

业务查询配置使用 `business_readonly`，但初始化流程需要真正创建该只读用户并授权指定表。

#### 7.11 文档去重范围不合理

SHA256 目前全局唯一。

应该使用 `(user_id, sha256)` 联合唯一约束，避免跨用户泄漏重复文件信息。

#### 7.12 缺少端到端证据

必须增加真实链路测试：

```text
API
→ 平台数据库 commit
→ Redis
→ Worker
→ 经营数据库
→ pgvector
→ Model Gateway
→ 结构化报告
→ GET 查询结果
```

`.run()` 单元测试不能代替真实 Redis + Worker 测试。

---

## 8. 推荐后端架构

```text
Web/API
  ↓
Authentication and Resource Scope
  ↓
AnalysisRun Service
  ↓
Platform PostgreSQL commit
  ↓
Celery Queue
  ↓
Analysis Worker
  ↓
Planner
  ├── Template Data Tool → Read-only Business PostgreSQL
  └── RAG Tool → User Documents / pgvector
  ↓
Deterministic Fact Builder
  ↓
LLM Report Composer
  ↓
Schema/Citation/Numeric/Basis Validators
  ↓
Analysis Report Persistence
  ↓
Polling API / Frontend
```

边界规定：

- API 不执行长分析。
- Worker 不信任客户端传来的用户 ID。
- Planner 不生成最终结论。
- Data Agent 不直接访问平台数据库。
- Knowledge Agent 不访问经营数据库。
- LLM 不执行 SQL。
- LLM 不决定权限。
- Reviewer 不替代确定性校验器。
- PostgreSQL 是任务状态唯一事实来源。
- Redis 只负责队列和短期协调。

---

## 9. 推荐代码目录

```text
backend/
├── app/
│   ├── api/
│   │   ├── auth.py
│   │   ├── health.py
│   │   ├── documents.py
│   │   ├── analysis_runs.py
│   │   └── router.py
│   │
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── document.py
│   │   ├── analysis_run.py
│   │   ├── analysis_plan.py
│   │   ├── data_request.py
│   │   ├── evidence.py
│   │   ├── analysis_report.py
│   │   └── error.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── documents.py
│   │   ├── document_chunk.py
│   │   ├── analysis_run.py
│   │   ├── analysis_run_document.py
│   │   ├── analysis_evidence.py
│   │   └── analysis_report.py
│   │
│   ├── repositories/
│   │   ├── user_repository.py
│   │   ├── document_repository.py
│   │   ├── chunk_repository.py
│   │   ├── analysis_run_repository.py
│   │   ├── evidence_repository.py
│   │   └── report_repository.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── document_service.py
│   │   ├── document_ingestion_service.py
│   │   ├── analysis_run_service.py
│   │   ├── analysis_orchestrator.py
│   │   ├── fact_builder.py
│   │   ├── report_composer.py
│   │   ├── report_validator.py
│   │   ├── citation_validator.py
│   │   ├── numeric_validator.py
│   │   └── coverage_calculator.py
│   │
│   ├── agents/
│   │   ├── protocol.py
│   │   ├── planner.py
│   │   ├── data.py
│   │   ├── knowledge.py
│   │   └── reviewer.py
│   │
│   ├── tools/
│   │   ├── protocol.py
│   │   ├── registry.py
│   │   ├── template_query.py
│   │   ├── business_query_registry.py
│   │   ├── business_semantic_catalog.py
│   │   ├── readonly_executor.py
│   │   └── rag.py
│   │
│   ├── workflows/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   └── graph.py
│   │
│   ├── tasks/
│   │   ├── analysis_tasks.py
│   │   └── document_tasks.py
│   │
│   ├── core/
│   │   ├── settings.py
│   │   ├── logging.py
│   │   ├── middleware.py
│   │   ├── exceptions.py
│   │   ├── celery_app.py
│   │   ├── security.py
│   │   └── gateway/
│   │       ├── base.py
│   │       ├── factory.py
│   │       ├── local.py
│   │       ├── openai.py
│   │       └── deepseek.py
│   │
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── business_session.py
│   │
│   └── main.py
│
├── migrations/
├── scripts/
│   ├── generate_business_data.py
│   ├── validate_business_data.py
│   ├── create_business_readonly_user.sql
│   └── verify_analysis_e2e.py
│
└── tests/
    ├── unit/
    │   ├── test_analysis_schemas.py
    │   ├── test_planner.py
    │   ├── test_fact_builder.py
    │   ├── test_report_validator.py
    │   ├── test_template_query_tool.py
    │   └── test_rag_tool.py
    ├── integration/
    │   ├── test_analysis_runs_api.py
    │   ├── test_analysis_permissions.py
    │   ├── test_analysis_worker.py
    │   ├── test_document_ingestion.py
    │   └── test_business_queries.py
    ├── e2e/
    │   └── test_analysis_run_e2e.py
    └── evaluation/
        ├── test_sales_decline_scenario.py
        ├── test_margin_decline_scenario.py
        ├── test_complaint_scenario.py
        ├── test_receivable_scenario.py
        └── test_insufficient_evidence.py
```

现有文件应逐步移动或演进，不要一次性大规模重命名。

---

## 10. 核心 API Schema

### 10.1 创建任务

```python
class AnalysisRunCreate(BaseModel):
    scenario: Literal[
        "regional_sales_decline",
        "gross_margin_decline",
        "complaint_increase",
        "receivable_risk",
    ]
    question: str
    region: RegionCode | None
    current_month: date
    comparison_month: date
    document_ids: list[int]
```

第一阶段只允许：

```python
scenario: Literal["regional_sales_decline"]
```

其他场景实现后再扩展 Literal，避免 Schema 承诺未实现功能。

### 10.2 任务状态

```python
class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

```python
class RunStage(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    QUERYING_DATA = "querying_data"
    RETRIEVING_DOCUMENTS = "retrieving_documents"
    BUILDING_FACTS = "building_facts"
    COMPOSING_REPORT = "composing_report"
    VALIDATING_REPORT = "validating_report"
    SAVING_RESULT = "saving_result"
    COMPLETED = "completed"
```

### 10.3 事实

```python
class ConfirmedFact(BaseModel):
    fact_id: str
    statement: str
    data_evidence_ids: list[str]
```

### 10.4 原因假设

```python
class Hypothesis(BaseModel):
    hypothesis_id: str
    statement: str
    related_fact_ids: list[str]
    citation_chunk_ids: list[int]
    support_level: Literal["low", "medium", "high"]
```

### 10.5 建议

```python
class Recommendation(BaseModel):
    recommendation_id: str
    priority: Literal["high", "medium", "low"]
    action: str
    rationale: str
    basis_fact_ids: list[str]
    basis_hypothesis_ids: list[str]
    verification_metric: str | None
```

### 10.6 最终报告

```python
class FinalAnalysisReport(BaseModel):
    schema_version: Literal["1.0"]
    status: Literal["completed", "partial", "failed"]
    scenario: Scenario

    executive_summary: str
    confirmed_facts: list[ConfirmedFact]
    hypotheses: list[Hypothesis]
    recommendations: list[Recommendation]

    data_evidence: list[DataEvidence]
    document_citations: list[DocumentCitation]
    limitations: list[Limitation]
```

---

## 11. 数据库规划

### 11.1 analysis_runs

保存：

- 用户输入。
- 结构化分析范围。
- 当前状态和阶段。
- 重试次数。
- Celery 任务 ID。
- 幂等键。
- 错误代码和错误信息。
- 开始、完成和取消时间。

### 11.2 analysis_run_documents

保存一次分析允许访问的文档范围。

联合唯一约束：

```text
analysis_run_id + document_id
```

### 11.3 analysis_evidence

保存数据证据和文档证据。

数据证据保存：

- query_id
- query_version
- parameters
- result
- row_count
- executed_at

文档证据保存：

- document_id
- chunk_id
- page_number
- excerpt
- retrieval_score

### 11.4 analysis_reports

保存：

- analysis_run_id
- schema_version
- report_data JSONB
- model_provider
- model_name
- prompt_version
- created_at

第一版使用经过 Pydantic 校验的 JSONB 是合理方案。

---

## 12. API 规划

```text
POST   /auth/login
GET    /auth/me
POST   /documents/upload
GET    /documents
GET    /documents/{id}
GET    /documents/{id}/chunks
DELETE /documents/{id}
POST   /analysis-runs
GET    /analysis-runs
GET    /analysis-runs/{id}
POST   /analysis-runs/{id}/cancel
POST   /analysis-runs/{id}/retry
GET    /health/live
GET    /health/ready

### POST /analysis-runs

职责：

1. 校验请求 Schema。
2. 校验所有文档属于当前用户。
3. 创建分析任务。
4. 提交数据库事务。
5. 提交 Celery 消息。
6. 返回 `202 Accepted`。

不得在请求中：

- 查询经营数据库。
- 调用 Embedding。
- 调用 LLM。
- 执行完整工作流。

---

## 13. 工作流规划

```text
queued
→ planning
→ querying_data
→ retrieving_documents
→ building_facts
→ composing_report
→ validating_report
→ saving_result
→ completed / partial
任何阶段都可能进入：
failed
cancelled
retrying
Planner
输入：
question
scenario
region
current_month
comparison_month
document_ids
输出：
标准化问题。
数据查询列表。
文档检索请求。
场景报告策略。
Data Agent
输入：
DataRequest。
输出：
DataEvidence。
限制：
只能使用 TemplateQueryTool。
不能自由执行 SQL。
不能访问平台用户和任务表。
Knowledge Agent
输入：
问题。
用户 ID。
允许的文档 ID。
输出：
DocumentCitation 列表。
是否证据充分。
Fact Builder
输入：
DataEvidence。
输出：
ConfirmedFact。
事实构建应以确定性代码为主。
Report Composer
输入：
事实。
文档引用。
场景规则。
输出：
FinalAnalysisReport 草稿。
Validators
必须执行：
Schema 校验。
引用存在性和权限校验。
事实与数据证据关系校验。
假设与文档引用关系校验。
建议与事实/假设关系校验。
completed、partial、failed 状态契约校验。
14. 可靠性要求
14.1 数据库提交和消息投递
任务必须先提交数据库，再调用 .delay()。
如果消息投递失败：
保存 queue_publish_failed。
不返回伪 completed。
允许重新投递。
后续可增加 Outbox。
14.2 幂等
Worker 开始时原子认领任务。
以下情况不得重复写报告：
Celery 重复投递。
Worker 重启。
网络超时导致调用方重试。
手工重复点击。
14.3 重试
只重试：
模型限流。
临时网络错误。
短暂数据库连接失败。
Redis 暂时不可用。
不重试：
Schema 校验失败。
无权限。
不支持的场景。
危险 SQL。
文档不存在。
引用造假。
14.4 取消
API 设置 cancelled 或 cancel_requested_at。
Worker 在每个阶段前检查。
取消后不得保存最终 completed 报告。
14.5 日志
所有分析日志至少包含：
request_id
user_id
analysis_run_id
stage
attempt_count
error_type
duration_ms
不得记录：
API Key。
数据库密码。
完整敏感文档。
未脱敏客户联系方式。
15. 测试与评测规划
单元测试
证明：
Schema 约束。
Planner 计划。
固定查询编译。
事实构建。
引用校验。
报告状态契约。
重试分类。
集成测试
证明：
FastAPI 依赖注入。
用户隔离。
数据库持久化。
任务 commit 后可被新 Session 读取。
固定查询能访问只读经营库。
文档检索不会跨用户。
E2E 测试
证明：
Redis 消息真实投递。
Worker 真实消费。
独立 Session 可见任务。
最终报告能通过 GET 查询。
场景评测
至少建立五个固定案例：
区域销售下降。
毛利下降。
客诉上升。
应收风险。
数据存在但原因文档不足。
评测指标：
查询参数正确率。
数据事实正确率。
引用有效率。
数字一致率。
拒答正确率。
报告 Schema 有效率。
工作流完成率。
P50/P95 执行时间。
单次模型 Token 和成本。
目标值只能在获得真实基线后确定，不能提前编造。
16. 实施阶段
阶段 0：恢复全绿基线
完成：
修复当前 4 个失败测试。
修复 Ruff。
核对迁移单一 head。
核对 Docker 环境变量。
创建经营数据库只读用户。
验收：
非 E2E 测试全绿。
Ruff 全绿。
Compose 配置有效。
经营账号不能写数据库。
阶段 1：结构化分析契约
完成：
AnalysisRunCreate。
RunStatus。
RunStage。
DataEvidence。
ConfirmedFact。
Hypothesis。
Recommendation。
FinalAnalysisReport。
验收：
Schema 单元测试全绿。
completed/partial/failed 非法组合被拒绝。
阶段 2：分析任务 API
完成：
/analysis-runs。
参数持久化。
文档范围。
用户隔离。
取消和重试入口。
验收：
创建返回 202。
第二用户读取返回 404。
数据库提交先于 .delay()。
阶段 3：销售下降数据链路
完成：
区域销售比较。
客户销售下钻。
TemplateQueryTool。
DataEvidence。
ConfirmedFact。
验收：
固定种子数据产生可复现事实。
用户和 LLM 都不能输入 SQL。
阶段 4：文档证据链路
完成：
限定 document_ids。
用户过滤。
引用片段、页码和分数。
证据充分性判断。
验收：
越权文档不返回。
无证据返回空引用和明确限制。
阶段 5：结构化报告
完成：
Report Composer。
引用校验。
事实依据校验。
建议依据校验。
partial/failed 规则。
验收：
报告包含事实、假设、建议、证据和限制。
编造引用被拒绝。
阶段 6：接通 Worker 和 LangGraph
完成：
Worker 调用完整工作流。
状态和节点映射。
保存报告后再 completed。
取消和分类重试。
验收：
API 到结果查询形成闭环。
重复执行不重复写报告。
阶段 7：扩展其他三类场景
按顺序：
毛利下降。
客诉上升。
应收风险。
每个场景必须先有：
需求。
DataRequest。
固定查询。
事实构建。
文档策略。
评测案例。
自动化测试。
阶段 8：安全和可观测
完成：
JWT 或安全 API Key 策略。
限流。
敏感数据脱敏。
Prompt 注入测试。
日志关联。
失败任务查询。
阶段 9：部署和运维
完成：
从零 Docker 启动。
数据迁移。
健康检查。
备份恢复。
Worker、Redis、数据库和模型故障 Runbook。
最小前端。
17. 每项功能完成定义
功能只有满足以下条件才算完成：
业务需求明确。
输入输出有 Schema。
数据库变化有迁移。
正常路径测试通过。
关键失败路径测试通过。
用户隔离测试通过。
日志能定位问题。
不泄漏密钥和敏感信息。
文档描述与实际代码一致。
能在 Docker 环境运行。
学习者能解释设计。
学习者能完成相似修改。
学习者能独立排查一个相关故障。
18. MVP 最终验收场景
用户 A 登录。
用户 A 上传至少两份业务文档。
Worker 成功解析并建立向量。
用户 A 创建区域销售下降分析。
API 返回 202。
Worker 使用独立 Session 取得任务。
Worker 使用只读经营账号查询数据。
报告包含至少一项确认事实。
报告包含至少一项有真实文档引用的假设。
报告包含至少一项有依据的建议。
数字能回溯到查询结果。
引用能回溯到当前用户文档 chunk。
文档不足案例返回 partial。
数据或模型完全失败案例返回 failed。
用户 B 无法读取用户 A 的文档、任务或报告。
重复投递不会生成重复报告。
取消任务不会继续保存最终结果。
可以通过日志定位任务执行阶段。
Docker 环境可以从零启动。
学习者能完整讲解、修改、验证和排错该链路。
达到以上标准后，项目才能称为：
一个真实可运行、具有可信证据链和基础可靠性的中小型企业经营分析助手。
