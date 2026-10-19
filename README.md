# Enterprise Insight Assistant（企业经营洞察助手）

面向中小型公司的证据驱动经营分析系统。用户用自然语言提出经营问题，系统在当前公司授权范围内查询只读经营数据库、检索内部文档，并生成可追溯的结构化报告。

本项目目标是全模块符合明确适用范围的生产级设计与工程要求，并在单电脑与存储服务环境完成真实验证，不要求上线。当前实现尚未通过整体生产级验收；目标与进度分开记录。

**查看计划与进度，从 [文档阅读导航](docs/README.md) 开始。**

## 已有模块与能力基础

以下是实现构成，不代表各项已通过完整生产级门禁；当前缺口与验证范围见 [项目审计](docs/audits/project_core_audit_20260915.md)。

- 公司级身份与权限：JWT 登录、成员角色、资源隔离和管理审批。
- 文档知识库：TXT、Markdown、PDF 上传，异步解析、分块、向量化和 pgvector 检索。
- 受控经营查询：Schema 快照、查询契约、`sqlglot` AST 校验、只读事务和结果约束。
- Agent 工作流：Planner → Data / Knowledge → Reviewer，支持条件路由、澄清和证据不足分支。
- 可信报告：事实、假设、建议、数据证据、文档引用和限制分别建模并交叉校验。
- 异步可靠性：Celery、Redis、Outbox、执行租约、Checkpoint、分类重试、取消和幂等发布。
- 人工审核与治理：待审核报告、模型调用记录、Tool 调用审计、任务事件和运行指标。
- React 工作台：经营问答、证据范围、文档库、数据源、成员管理和任务状态展示。

## 系统边界

系统只接受经营问题，不接受用户提交的原始 SQL，也不允许 LLM 决定权限或写入经营数据库。

```text
React / TypeScript
        │ HTTP + JWT
        ▼
FastAPI ── PostgreSQL + pgvector
        │ commit + Outbox
        ▼
Redis ── Celery Worker ── LangGraph
                           ├─ Planner
                           ├─ Data Agent ── 只读经营数据库
                           ├─ Knowledge Agent ── 当前公司文档
                           └─ Reviewer + 确定性校验器
                                      │
                                      ▼
                              持久化结构化报告
```

关键约束：

- API 只负责校验、鉴权、持久化和任务投递，不在 HTTP 请求中执行长分析。
- Worker 只接收 `task_id`，从数据库恢复冻结的公司、数据源、Schema 和文档范围。
- Data Agent 生成的候选 SQL 必须通过查询契约、Schema、AST 和只读执行边界。
- Knowledge Agent 只能引用本次任务允许访问的文档分块。
- Reviewer 只能组织已验证证据，最终发布仍由确定性校验和持久化门控制。
- 数据确认的是事实；文档支持的是原因假设。证据不足时返回限制或澄清，不伪造归因。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| API | Python 3.10+、FastAPI、Pydantic |
| 数据与迁移 | PostgreSQL、SQLAlchemy 2、Alembic、pgvector |
| 异步执行 | Celery、Redis、Outbox |
| Agent 编排 | LangGraph、结构化模型输出 |
| 检索 | sentence-transformers、向量检索、Reranker |
| 经营查询 | `sqlglot`、Schema Snapshot、只读 PostgreSQL |
| 认证 | JWT、Argon2、角色权限 |
| 前端 | React、TypeScript、Vite |
| 本地部署 | Docker Compose、PowerShell 运维脚本 |

## 快速开始

### 前置条件

- Docker Desktop（推荐）
- 或 Python 3.10+、Node.js 20+、PostgreSQL、Redis

### Docker Compose

```powershell
Copy-Item backend/.env.example backend/.env
# 编辑 backend/.env：至少设置模型 Provider/API Key，并更换生产环境密码与 JWT_SECRET。

docker compose up -d --build
docker compose ps
```

Compose uses a lightweight core image for the API, migrations, Beat, and report
Worker. The analysis Worker uses a separate CPU-only local-model image because
document embedding and reranking require PyTorch. A GPU embedding service is
not enabled by default; it requires a separately versioned internal call
contract and is not substituted by `gpus: all`.

服务入口：

- 前端：http://localhost:5173
- API：http://localhost:8000
- OpenAPI：http://localhost:8000/docs
- 平台 PostgreSQL：`localhost:5433`
- Redis：`localhost:6380`
- 演示经营库：`localhost:5434`、`5435`、`5436`

首次使用可通过 `POST /auth/bootstrap-owner` 创建首个公司所有者；请求结构以 OpenAPI 页面为准。

停止服务：

```powershell
docker compose down
```

`docker compose down -v` 会删除本地数据库卷，不应作为普通停止命令使用。

### 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

Set-Location backend
pip install -e ".[dev]"
# 仅在本机运行真实 RAG/slow 测试时安装本地 CPU 模型依赖；普通 API
# 开发和测试不需要它。
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
pip install -r requirements/ml.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

新终端启动 Worker：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m celery -A app.core.celery_app:celery_app worker --loglevel=INFO
```

新终端启动前端：

```powershell
Set-Location frontend
npm ci
npm run dev
```

## 验证

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m pytest tests -q -m "not e2e and not slow"

Set-Location ..\frontend
npm test
npm run build

Set-Location ..
docker compose config --quiet
```

普通单元/集成测试不能证明真实 Redis、独立 Celery Worker、经营数据库和模型 Provider 的完整链路。需要真实依赖时，按测试标记和 [单机运行与恢复 Runbook](docs/operations/single_node_runbook.md) 执行对应 E2E。

## 主要 API

- `/auth/*`：登录、当前用户、密码和成员申请。
- `/documents/*`：文档上传、编辑、处理状态和分块查询。
- `/conversations/*`：会话、消息、分析任务创建与结果读取。
- 任务操作位于会话主链；旧 `/tasks/*` 路由当前未在 `backend/app/api/router.py` 挂载。
- 附件输入接口由 `input_artifacts` 模块提供，实际路径以 OpenAPI 为准。
- `/company/*`：公司、成员、邀请、数据源和 Schema 快照。
- `/review-requests/*`：报告审核。
- `/observability/*`：任务指标。
- `/health/live`、`/health/ready`：存活与就绪检查。

完整契约以运行时 OpenAPI 为准。

## 仓库结构

```text
backend/
  app/
    api/ core/ db/      路由组合、配置/网关/Celery、数据库会话
    modules/<领域>/     业务领域：api / schemas / service / repository / models / tasks
                        大模块按职责分子包，如 workflow/{orchestration,lifecycle,delivery,audit}
  migrations/           Alembic 迁移链
  tests/{unit,integration,scripts,fixtures}
  scripts/{data,evaluation,ops,db}
  docker/               api / worker / evaluation 镜像定义
  requirements/         base / ml / evaluation 依赖
frontend/src/           React 工作台
data/business_knowledge_base/  可复现演示语料
docs/                   计划、架构、设计稿、运维、审计、证据（见 docs/README.md）
scripts/ops/            备份、恢复、队列和权限检查
docker-compose.yml      本地服务编排
```

完整说明见 [目录结构与模块边界](docs/architecture/modular_monolith_structure.md)。

## 项目文档

- [文档索引](docs/README.md)
- [当前执行计划：改进与学习计划](docs/plans/improvement_and_learning_plan.md)
- [目录结构与模块边界](docs/architecture/modular_monolith_structure.md)
- [证据记录](docs/evidence.md)
- [最终设计范围路线图](docs/plans/single_node_production_style_ai_application_roadmap.md)
- [产品定义与边界](PRODUCT.md)
- [前端设计系统](DESIGN.md)
- [单机运行与故障恢复](docs/operations/single_node_runbook.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)

## 许可证

当前仓库尚未声明开源许可证。除非仓库所有者补充 LICENSE，否则默认不授予复制、修改或分发许可。
