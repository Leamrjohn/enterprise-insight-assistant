# Enterprise Insight Assistant（企业经营洞察助手）

面向企业内部经营分析场景的 Multi-Agent AI 平台。用户提出经营问题，系统从已授权的只读经营数据库和当前用户文档知识库中取证，输出可追溯的结构化经营分析报告——包含事实、原因假设、建议行动、数据证据、文档引用和限制。

> 当前为教学/演示项目，第一版支持四类固定场景：区域销售下降、毛利下降、客诉上升、应收风险。

## 架构

```text
                    ┌──────────────┐
                    │   React SPA   │
                    │ (Vite + TS)  │
                    └──────┬───────┘
                           │ HTTP / JWT
                    ┌──────▼───────┐
                    │   FastAPI    │
                    │  (REST API) │
                    └──┬───────┬───┘
                       │       │
              ┌────────▼──┐ ┌──▼─────────┐
              │ PostgreSQL │ │   Redis     │
              │ (pgvector) │ │ (Celery Q) │
              └────────────┘ └──┬─────────┘
                                │
                        ┌───────▼────────┐
                        │  Celery Worker  │
                        │  ┌─────────────┐│
                        │  │  LangGraph   ││
                        │  │  Planner     ││
                        │  │  Data Agent  ││
                        │  │  Knowledge   ││
                        │  │  Reviewer    ││
                        │  └─────────────┘│
                        └───────┬─────────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
            ┌───────▼──┐ ┌─────▼────┐ ┌────▼──────┐
            │ Business │ │ pgvector │ │   Model    │
            │   DB     │ │  (RAG)   │ │  Gateway   │
            │ (只读)   │ └──────────┘ │(DeepSeek等)│
            └──────────┘             └───────────┘
```

核心设计原则：
- **API 不执行长分析** — 仅校验、创建任务、提交 Celery
- **Data Agent 只执行固定查询模板** — 用户和 LLM 不能输入原始 SQL
- **Knowledge Agent 只检索当前用户文档** — 不访问经营数据库
- **LLM 不计算数字** — 由确定性代码从查询结果构建事实
- **引用和数字经确定性校验** — Reviewer 不替代 Pydantic 校验器

## 当前能力

### 已实现

- **FastAPI 应用** — 分层架构：API → Service → Repository → Model，带依赖注入、请求 ID 追踪、结构化日志
- **JWT 认证** — 用户名密码登录、密码哈希（argon2）、公司隔离、角色授权（owner/admin/analyst/viewer）
- **公司成员管理** — 邀请码入职、成员申请审核、角色变更、禁启用、最后一位所有者保护
- **文档知识库** — TXT/PDF/Markdown 上传、异步解析分块、Embedding（sentence-transformers）、pgvector 向量检索 + Reranker
- **经营数据源** — 多公司只读数据库连接、Schema 快照发现、契约版本管理、凭据环境变量隔离
- **受控 SQL 查询** — 固定查询模板（TemplateQueryTool）+ 业务语义目录 + SQL AST 校验（sqlglot）+ 只读事务
- **LangGraph 工作流** — Planner → Data Agent → Knowledge Agent → Reviewer，含条件路由、重试、空结果重规划
- **Celery 异步分析** — 原子认领任务、独立数据库 Session、阶段持久化、重试/取消、幂等保护
- **结构化报告** — `FinalAnalysisReport`（Pydantic），包含 ConfirmedFact、Hypothesis、Recommendation、DataEvidence、DocumentCitation、Limitation 及交叉校验
- **Docker Compose** — 一键启动 11 个服务（PostgreSQL + Redis + API + Worker + Beat + 业务数据库 + 前端）
- **216 个非 E2E 测试通过**（2 个需要 Docker 业务数据库的测试标记跳过）

### 规划中

- 完成四类场景的端到端验收数据
- E2E 测试（真实 Redis + Worker + 业务库链路）
- 场景评测集（Recall@K、引用有效率、数字一致率）
- 限流、脱敏、Prompt 注入防护
- 部署 Runbook 和备份恢复

## 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI (Python 3.10+) |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic |
| 向量数据库 | pgvector |
| 向量模型 | sentence-transformers / BAAI/bge-reranker-base |
| 异步任务 | Celery + Redis |
| Agent 编排 | LangGraph |
| SQL 校验 | sqlglot |
| LLM 网关 | OpenAI / DeepSeek 兼容接口 |
| 认证 | PyJWT + argon2-cffi |
| 前端 | React + TypeScript + Vite |
| 容器化 | Docker Compose |

## 快速开始

### 环境要求

- Python 3.10+
- Docker Desktop（或 Node.js 20+ 用于前端）
- PostgreSQL（用于本地开发，Docker 内已包含）

### Docker 一键启动

```powershell
docker compose up -d
```

启动后：
- API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 前端: http://localhost:5173
- PostgreSQL 平台库: localhost:5433
- 业务演示库 (Acme): localhost:5435
- 业务演示库 (Beta): localhost:5436

### 本地开发

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装依赖
cd backend
pip install -e ".[dev]"

# 3. 配置环境变量
Copy-Item .env.example .env
# 编辑 .env 填入数据库密码等

# 4. 初始化数据库
..\.venv\Scripts\python.exe -m alembic upgrade head

# 5. 启动 API
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 6. 启动 Worker（新终端）
..\.venv\Scripts\python.exe -m celery -A app.core.celery_app worker --loglevel=INFO

# 7. 启动前端（新终端）
cd frontend
npm ci
npm run dev
```

### 运行测试

```powershell
cd backend

# 快速测试（跳过需要 Docker 的 E2E 和慢速测试）
..\.venv\Scripts\python.exe -m pytest tests/ -q -m "not e2e and not slow"

# 代码检查
..\.venv\Scripts\python.exe -m ruff check app tests
```

## 仓库结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # HTTP 接口（auth, documents, conversations, companies, tasks）
│   │   ├── schemas/      # Pydantic 输入输出和结构化报告契约
│   │   ├── models/       # SQLAlchemy ORM 模型
│   │   ├── repositories/ # 数据访问层
│   │   ├── services/     # 业务逻辑（文档处理、工作流、校验器）
│   │   ├── agents/       # Planner, Data, Knowledge, Reviewer Agent
│   │   ├── tools/        # 受控 SQL、RAG、TemplateQuery、校验器
│   │   ├── tasks/        # Celery 任务入口
│   │   ├── core/         # 配置、日志、中间件、Model Gateway
│   │   └── db/           # 数据库会话（平台 + 业务只读）
│   ├── migrations/       # Alembic 迁移
│   ├── scripts/          # 种子数据、业务库初始化
│   └── tests/            # 216 个通过的测试
├── frontend/
│   └── src/              # React SPA（经营助手、文档库、数据源管理、用户中心）
├── docs/                 # 产品规划、教学计划、设计系统
├── docker-compose.yml    # 11 个服务的编排
└── AGENTS.md             # AI Agent 教学与协作规则
```

## 设计文档

详见 `docs/` 目录：
- [项目计划](docs/项目计划.md) — 9 阶段交付计划
- [后端产品交付](docs/backend_product_delivery_plan.md) — 架构、Schema、API、数据库规划
- [产品目标](docs/project_goal_enterprise_insight_assistant.md) — MVP 范围与验收标准
- [设计系统](DESIGN.md) — 前端色彩、排版、组件规范
- [产品定位](PRODUCT.md) — 用户角色、能力边界、品牌承诺
