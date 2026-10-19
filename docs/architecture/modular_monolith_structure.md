# 目录结构与模块边界

> 本文是仓库目录的唯一权威说明：每个文件放在哪里、为什么放在那里、模块之间怎么调用。实施顺序以 [改进与学习计划](../plans/improvement_and_learning_plan.md) 为准。
> 最近一次调整：2026-10-19（仓库级整理 + workflow / analysis / input_artifacts 分子包）。

## 1. 仓库顶层

```text
.
├── README.md / AGENTS.md / CONTRIBUTING.md / SECURITY.md   入口说明、协作规则、贡献与安全
├── PRODUCT.md / DESIGN.md      产品定义、前端设计系统（设计工具约定放在根目录）
├── docker-compose.yml          本地全栈编排（API、Worker、Beat、PG、Redis、ClamAV、LocalStack…）
├── backend/                    Python 后端（FastAPI + Celery + LangGraph）
├── frontend/                   React + Vite 工作台
├── data/
│   └── business_knowledge_base/  可复现的演示语料（由脚本生成，勿手改）
├── docs/                       全部项目文档（索引见 docs/README.md）
└── scripts/ops/                面向整套环境的运维脚本（PowerShell）：备份、恢复演练、队列、RLS、只读检查
```

本地生成、不进 Git 的目录：`tmp/`、`artifacts/`、`evaluation-runs/`、`backend/.evaluation-runs/`、`backend/logs/`、`backend/storage/`、`.venv*/`。

## 2. backend

```text
backend/
├── app/                    应用代码（见第 3 节）
├── migrations/             Alembic 迁移链（env.py 显式导入全部 ORM 模型）
├── tests/
│   ├── unit/<领域>/         单元与契约测试，按 app/modules 领域镜像
│   ├── integration/<领域>/  依赖真实 PostgreSQL / Redis 的集成测试（使用隔离库 agent_platform_test）
│   ├── scripts/            运维与评测脚本的测试
│   ├── fixtures/evaluation/ 评测 Case 与阈值（内容冻结，改动会改变 SHA）
│   └── conftest.py
├── scripts/
│   ├── data/               业务演示库与语料：生成、灌入、校验
│   ├── evaluation/         业务评测：准备、运行、轨迹渲染、P0 候选实验
│   ├── ops/                容量信号服务、文档摄取 E2E 校验
│   └── db/                 PostgreSQL 初始化 SQL（compose 挂载）
├── docker/                 镜像定义：api / worker / evaluation / evaluation-full .Dockerfile
├── requirements/           base（运行时）/ ml（本地模型）/ evaluation / evaluation-full
├── pyproject.toml          包与工具配置（pytest、ruff）
├── alembic.ini
└── .env.example / .env.p0.example
```

## 3. backend/app

```text
app/
├── main.py           应用启动与装配
├── api/router.py     唯一 HTTP 路由组合点，不含业务逻辑
├── core/             跨领域技术能力：配置、日志、异常、中间件、安全、Celery 应用、模型网关(gateway/)
├── db/               SQLAlchemy Base、会话与租户范围、数据库时钟
├── utils/            无业务语义的小工具
└── modules/          按业务领域组织（见第 4 节）
```

## 4. 领域模块

每个领域尽量使用同一套文件名，打开任何模块都能按名字找到对应层：

| 文件 | 职责 |
|---|---|
| `api.py` | HTTP 入口：参数校验、依赖注入、调用 service，不写业务规则 |
| `schemas.py` | 对外的 Pydantic 输入输出契约 |
| `service.py` | 业务规则与事务边界 |
| `repository.py` | 数据库读写 |
| `models.py` | SQLAlchemy ORM 模型 |
| `tasks.py` / `outbox_tasks.py` | Celery 任务入口（**固定放在模块根目录**，Celery 任务名依赖此路径） |

| 模块 | 职责 | 子包 |
|---|---|---|
| `identity` | 用户、登录、JWT | — |
| `organizations` | 公司、成员、角色、邀请、经营数据源、Schema 快照 | — |
| `conversations` | 会话、消息、分析任务创建入口、会话上下文 | — |
| `workflow` | 分析任务引擎 | `orchestration/` LangGraph 图、节点、路由、状态<br>`lifecycle/` 认领与租约、执行尝试、Checkpoint、恢复、状态转换表、任务规格、版本、发布、容量、模型预算<br>`delivery/` Outbox 事件与投递<br>`audit/` 工作流事件、模型调用与工具调用记录 |
| `analysis` | Planner 与数据分析 | `planner/` 意图、计划、决策<br>`data/` Data Agent、SQL 生成/校验/执行、查询契约与注册表、模板查询<br>`catalog/` Schema 发现、语义目录、快照目录<br>`metrics/` 指标目录与校验、事实构建、数值断言校验<br>根目录：`agent_protocol.py`、`tool_protocol.py`（跨子包共享协议） |
| `knowledge` | RAG：检索、重排、证据、MCP 证据工具 | `rag/` |
| `documents` | 文档上传、切块、向量化、可见性 | — |
| `input_artifacts` | 附件输入（**冻结**） | `upload/` 上传请求、会话、直传、指纹<br>`processing/` 扫描、解析、OCR、处理作业与 Outbox<br>根目录：api、models、schemas、repository、storage、versions、attachment_context |
| `reporting` | 报告 Schema、Composer、Reviewer、引用/数字/语义校验 | — |
| `reviews` | 人工审核 | — |
| `runtime` | ToolRuntime（工具唯一执行边界）、模型调用治理 | — |
| `memory` | 长期记忆读写 | — |
| `observability` | 健康检查、指标、拒绝审计 | — |
| `evaluation` | 业务评测器、Observation、阈值、结果指纹 | — |

后续阶段改造某个模块时，若文件数超过约 10 个，按职责拆子包，保持与上表同样的命名方式，并在本表登记。

## 5. 依赖规则

- `api` → `service` → `repository` / `models`；反向依赖禁止。
- 跨领域调用只走对方的 `service` 或明确的契约函数，不直接读写对方的表。
- 只有 `runtime/tool_runtime.py` 能执行工具；Agent 节点拿到的是被包装后的工具。
- `core/`、`db/` 不得依赖 `modules/`。
- Celery 任务名固定为 `app.modules.<领域>.tasks.<函数>` 或 `...outbox_tasks.<函数>`；移动任务函数等于修改对外契约，必须同步 beat 配置并处理队列中的旧消息。

## 6. 目录调整的验证要求

1. 全部模块可导入（`pkgutil.walk_packages` 逐个导入无错误）；
2. 代码、测试、Alembic、Celery、compose、Dockerfile、运维脚本中无旧路径；
3. 单元、脚本、集成测试结果与调整前一致；
4. 纯目录调整不改表结构、HTTP 路径、任务名、任务状态或业务语义。

2026-10-19 调整的验证结果见 `docs/evidence.md` 同日记录。
