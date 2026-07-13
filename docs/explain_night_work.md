# 2026-07-12 凌晨 Docker + pgvector + 向量搜索 实操全记录

## 一、Docker 环境搭建

### 1.1 检查 Docker 状态
```bash
docker info                 # 检查引擎是否运行
docker compose ps           # 检查容器状态
```

### 1.2 拉取镜像
```bash
docker pull pgvector/pgvector:0.8.0-pg16   # 带 pgvector 的 PostgreSQL 镜像
```

### 1.3 docker-compose.yml 修改

**修改1：** 普通 postgres:16 → 带 pgvector 的镜像
```yaml
image: pgvector/pgvector:0.8.0-pg16
```

**修改2：** 端口从 5432 改为 5433（因为本机 PG 在用 5432）
```yaml
ports:
  - "5433:5432"
```

**Docker 服务状态（凌晨2:20）:**
```
agent-platform-postgres   pgvector/pgvector:0.8.0-pg16   Up (healthy)   0.0.0.0:5433->5432
agent-platform-redis      redis:7                        Up (healthy)   0.0.0.0:6379->6379
```

### 1.4 .env 配置修改
```env
DATABASE_PORT=5433
DATABASE_PASSWORD=changeme_in_production
```

---

## 二、数据库迁移

### 2.1 清空旧迁移标记
```bash
docker compose exec -T postgres psql -U agent_app -d agent_platform \
  -c "DROP TABLE IF EXISTS alembic_version;"
```

### 2.2 创建测试数据库
```bash
docker compose exec -T postgres psql -U agent_app -d agent_platform \
  -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;"
docker compose exec -T postgres psql -U agent_app -d agent_platform \
  -c "CREATE DATABASE agent_platform_test OWNER agent_app;"
```

### 2.3 运行迁移
```bash
cd backend; .venv\Scripts\alembic.exe upgrade head
```
成功执行 8 个迁移步骤。

### 2.4 验证 pgvector 扩展
```bash
docker compose exec -T postgres psql -U agent_app -d agent_platform \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
# 输出：vector | 0.8.0
```

---

## 三、向量搜索实操

### 3.1 新建文件：`backend/scripts/vector_demo.py`
测试 pgvector 基本功能：创建 vector(384) 列、插入数据、查询。

### 3.2 新建文件：`backend/scripts/vector_search_demo.py`
端到端向量搜索演示：
1. 加载 `all-MiniLM-L6-v2` 模型
2. 5 条文档 → 384 维向量 → 存入 pgvector
3. 搜索"销售额为什么下降"
4. 返回按余弦距离排序的结果

**运行结果：**
```
搜索: 「销售额为什么下降」
[0.5209] 公司推出了新产品，预计下季度销售额回升
[0.5125] 去年销售额下降了15%，主要原因是市场竞争加剧
[0.4504] 今天天气很好，适合户外活动
```

### 3.3 新建文件：`backend/scripts/eval_demo.py`
评测代码——计算 Precision@K 和 Recall@K：

```python
# 核心评测逻辑
found_ids = set(r.id - 1 for r in results)
hits = len(found_ids & relevant)      # 命中的相关文档数
precision = hits / top_k              # 返回的结果中有多少比例是相关的
recall = hits / len(relevant)         # 所有相关文档中有多少比例被找到了
```

**评测结果：**
| 问题 | K | Precision | Recall |
|---|---|---|---|
| 销售额为什么下降 | 1 | 0.00 | 0.00 |
| 销售额为什么下降 | 3 | 0.33 | 1.00 |
| 成本上升的原因 | 1 | 1.00 | 1.00 |

---

## 四、Worker 替换为真实向量搜索

### 4.1 修改文件：`backend/app/tasks/analysis_tasks.py`

**改动1：** 新增导入
```python
from app.core.embeddings_local import LocalEmbeddingProvider
from app.repositories.vector_repository import search_similar_chunks
```

**改动2：** 新增 Embedder 懒加载
```python
_embedder = None

def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = LocalEmbeddingProvider()
    return _embedder
```

**改动3：** `_search_evidence` 从模拟数据改成真实向量搜索

```python
# 原来（模拟数据）
def _search_evidence(db, question, user_id):
    return [
        EvidenceRef(chunk_id=1, content="销售额下降了15%...", score=0.92),
        EvidenceRef(chunk_id=2, content="成本上升了10%...", score=0.85),
    ]

# 现在（真实 pgvector 搜索）
def _search_evidence(db, question, user_id):
    embedder = _get_embedder()
    embedding = embedder.embed(question)
    results = search_similar_chunks(db=db, embedding=embedding, user_id=user_id, top_k=3, min_score=0.3)
    return [EvidenceRef(chunk_id=r["chunk_id"], document_id=r["document_id"], content=r["content"], score=r["score"]) for r in results]
```

### 4.2 测试验证
```bash
24 passed ✅
```

---

## 五、当前完整数据流

```
用户 POST /tasks {"question":"销售额为什么下降"}
  → API 创建 task（status=queued）
  → Celery Worker 收到消息
    → 改状态为 running
    → _search_evidence:
        1. LocalEmbeddingProvider.embed(question) → 384维向量
        2. search_similar_chunks(db, embedding, user_id) → pgvector 余弦搜索
        3. 返回 EvidenceRef 列表
    → check_sufficiency（平均分 >= 0.4？）
    → build_prompt（组装证据+问题成 Prompt）
    → gateway.chat(prompt)（调用本地模拟 AI）
    → 保存结果到 task.result_summary
    → 改状态为 completed
  → 用户 GET /tasks/{id} 查看结果
```

---

## 六、阶段5补强计划

### 6.1 Docker Compose 结构

```yaml
services:
  postgres:       # 服务名
    image: pgvector/pgvector:0.8.0-pg16  # 镜像
    container_name: agent-platform-postgres  # 容器名
    environment:       # 环境变量
      POSTGRES_USER: agent_app
      POSTGRES_PASSWORD: changeme_in_production
      POSTGRES_DB: agent_platform
    ports:
      - "5433:5432"    # 宿主机端口:容器端口
    volumes:
      - postgres_data:/var/lib/postgresql/data  # 数据持久化
      - ./backend/scripts/bootstrap_postgres.sql:/docker-entrypoint-initdb.d/bootstrap.sql
    healthcheck:       # 健康检查
      test: ["CMD-SHELL", "pg_isready -U agent_app"]
      interval: 5s

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  postgres_data:       # 命名卷，数据不会因为容器删除而丢失
```

### 6.2 常用 Docker 命令

| 命令 | 作用 |
|---|---|
| `docker compose up -d` | 后台启动所有服务 |
| `docker compose down` | 停止并删除所有容器 |
| `docker compose ps` | 查看服务状态 |
| `docker compose logs postgres` | 查看 PostgreSQL 日志 |
| `docker compose exec postgres psql -U agent_app -d agent_platform` | 进入 PostgreSQL 交互终端 |
| `docker compose pull` | 拉取最新镜像 |
| `docker compose restart` | 重启服务 |

### 6.3 启动流程（4步）

```
第1步：docker compose up -d         → 启动 PostgreSQL + Redis
第2步：alembic upgrade head         → 创建/更新表结构
第3步：pytest -q                    → 验证
第4步：uvicorn app.main:app --reload → 启动开发服务
```

日常开发通常只需要第3步和第4步。

### 6.4 多环境配置

| 配置项 | development | production |
|---|---|---|
| APP_ENV | development | production |
| APP_DEBUG | true/false | false |
| LOG_LEVEL | INFO | WARNING |
| DATABASE_HOST | 127.0.0.1 | 正式数据库 IP |
| DATABASE_PASSWORD | 开发密码 | 高强度密码 |
| CORS_ORIGINS | localhost | 实际前端域名 |

### 6.5 测试数据库

- 测试时自动使用 `agent_platform_test` 数据库（由 conftest.py 控制）
- 测试数据库与开发数据库严格分离
- 每次测试独立创建和销毁
