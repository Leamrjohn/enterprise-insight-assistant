# 项目完整请求路径讲解

## 一、项目分层结构

```
┌─────────────────────────────────────────────────────────┐
│                   客户端（浏览器/API工具）                  │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP 请求/响应
┌──────────────────▼──────────────────────────────────────┐
│  API 层（app/api/）        路由注册 + HTTP 参数校验       │
│  router.py → 汇总所有子路由                              │
├─────────────────┬───────────────────────────────────────┤
│  Service 层（app/services/）  业务逻辑编排                │
├─────────────────┬───────────────────────────────────────┤
│  Repository 层（app/repositories/） 数据库操作            │
├─────────────────┬───────────────────────────────────────┤
│  Model 层（app/models/）      ORM 表映射                 │
│  + pgvector 向量搜索                                     │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  PostgreSQL + pgvector               Redis + Celery     │
│  （数据存储）                         （消息队列+Worker）  │
└─────────────────────────────────────────────────────────┘
```

## 二、所有已注册的路由

`router.py` 中注册了 5 个模块：

| 路由文件 | 路径前缀 | 提供的接口 |
|---|---|---|
| `health.py` | /health | GET /health |
| `auth.py` | /auth | GET /auth/me |
| `document.py` | /documents | GET/POST /documents, GET/PUT/DELETE /documents/{id}, POST /documents/upload, GET /documents/{id}/chunks |
| `chat.py` | /chat | （mock，未实现） |
| `tasks.py` | /tasks | POST /tasks, GET /tasks, GET /tasks/{id} |

---

## 三、完整调用链：逐个请求解析

### 路线1：健康检查 GET /health

这是最简单的请求，用来检测服务是否正常。

**完整路径：**

```
客户端 GET /health
  ↓
router.py 匹配到 health_router
  ↓
app/api/health.py → get_health()
    ↓
调用 health_service.py → get_health_service()
    ↓
调用 health_repository.py → check_database() → SELECT 1
    ↓
返回 {"status": "ok", "database": "connected"}
```

**经过的文件：**
api/health.py → services/health_service.py → repositories/health_repository.py

---

### 路线2：创建文档 POST /documents

手动创建一个文档记录（非上传文件）。

**请求体：** `{"name": "报告", "content": "内容...", "source": "manual"}`

**完整路径：**

```
客户端 POST /documents
  ↓
中间件 request_context_middleware（生成 Request ID，记录日志）
  ↓
router.py 匹配到 document_router
  ↓
Pydantic 校验请求体 → DocumentCreate（name/content/source 不能为空）
  ↓
app/api/document.py → create_document()
    ↓ 参数：request_model: DocumentCreate, current_user: User, db: Session
    ↓
app/services/document_service.py → save_document_service()
    ↓ 参数：db, user_id, name, content, source
    ↓
app/repositories/document_repository.py → save_document()
    ↓ 创建 Documents ORM 对象 → db.add() → db.commit() → db.refresh()
    ↓
返回 ORM 记录给 Service → Service 转为 dict
    ↓
返回给 API → FastAPI 用 DocumentOut 校验并序列化
    ↓
返回给客户端：{"id": 1, "name": "报告", "content": "内容...", ...}
```

---

### 路线3：上传文档 POST /documents/upload

上传文件，自动解析分块，存到数据库。

```
客户端 POST /documents/upload（multipart/form-data，文件字段叫 file）
  ↓
中间件（Request ID）
  ↓
Pydantic → UploadFile = File(...)
  ↓
API → upload_document()
  ↓
① file_storage_service.py → save_document_file()
    ↓ 校验文件名、后缀、大小
    ↓ 流式写入磁盘，计算 SHA256
    ↓ 返回 StoredDocumentFile（含路径、大小、SHA256）
    ↓
② document_ingestion_service.py → upload_document_service()
    ↓ SHA256 查重（已有则抛 DuplicateDocumentError）
    ↓ 创建 Documents 记录（source="upload", status="pending"）
    ↓ db.commit() + db.refresh()
    ↓ 返回 record
    ↓
③ document_ingestion_service.py → process_document_chunks()
    ↓ 读取文件
    ↓ utils/document_chunk.py → chunk_file() → 按段落分块
    ↓ 对每个 chunk：repositories/chunk_repository.py → add_chunk()
    ↓ 更新 document.status = "completed"
    ↓ db.commit()
    ↓
返回给客户端 Documents ORM → DocumentOut 序列化
```

**关键函数调用关系：**
```
api/document.py:upload_document
  → services/file_storage_service.py:save_document_file
  → services/document_ingestion_service.py:upload_document_service
    → repositories/document_repository.py:add_uploaded_document
    → repositories/document_repository.py:get_document_by_sha256
  → services/document_ingestion_service.py:process_document_chunks
    → utils/document_chunk.py:chunk_file → chunk_text
    → repositories/chunk_repository.py:add_chunk
```

---

### 路线4：创建分析任务 POST /tasks（核心业务）

这是最复杂的流程，涉及异步 Worker 和 RAG 引擎。

```
客户端 POST /tasks {"question": "销售额为什么下降"}
Header: X-API-Key: xxx
  ↓（第1阶段：同步处理）
中间件 → 生成 Request ID
  ↓
Pydantic → TaskCreate（校验 question 不为空）
  ↓
API → app/api/tasks.py → create_task()
  ↓
service → task_service.py → create_task_service()
  ↓
repository → task_repository.py → create_task()
    ↓ 创建 AnalysisTask(user_id, question, status="queued")
    ↓ db.flush() → 拿到 id
    ↓ db.refresh() → 返回 record
  ↓
API 层：
    db.commit()          ← 提交事务
    db.refresh(record)   ← 刷新数据
    ↓
  process_analysis_task.delay(task_id=record.id, user_id=current_user.id)
    ↑ Celery：把参数序列化成 JSON → 发到 Redis
    ↑ API 立刻返回给客户端，不等待 Worker 处理
    ↓
返回客户端：{"id": 5, "status": "queued", ...}

  ═══════════════════════════════════════
  （第2阶段：异步处理 — Worker 在后台执行）
  ═══════════════════════════════════════

Celery Worker 从 Redis 取出消息
  ↓
tasks/analysis_tasks.py → process_analysis_task(task_id, user_id)
  ↓
① 查数据库：
    db = SessionLocal()               ← Worker 自己创建数据库连接
    record = AnalysisTask.query(id=task_id)
  ↓
② 改状态为 running：
    record.status = "running"
    db.commit()
  ↓
③ **RAG 检索证据**：
    _search_evidence(db, question, user_id)
      ↓
    _get_embedder() → LocalEmbeddingProvider
      ↓
    embedder.embed("销售额为什么下降")
      ↓ sentence-transformers 模型
      ↓ 返回 384 维向量 [0.12, 0.45, -0.33, ...]
      ↓
    search_similar_chunks(db, vector, user_id, top_k=3, min_score=0.3)
      ↓ vector_repository.py
      ↓ 执行 SQL：
        SELECT content, 1 - (embedding <=> '[0.12,...]') AS score
        FROM document_chunks
        JOIN documents ON ...
        WHERE user_id = ? AND score > 0.3
        ORDER BY score DESC LIMIT 3
      ↓ pgvector 余弦距离搜索
      ↓ 返回 [{"chunk_id":1, "content":"销售额下降...", "score":0.92}, ...]
      ↓
    转成 EvidenceRef 列表返回
  ↓
④ **判断证据是否充分**：
    check_sufficiency(evidences, min_evidences=1, min_avg_score=0.4)
    ↓ 计算平均分：sum(scores) / len
    ↓ 不充分 → 直接返回"无法回答"
    ↓ 充分 → 继续
  ↓
⑤ **组装 Prompt 并调用 AI**：
    build_prompt(question, evidences)
      ↓ 把证据和问题拼成一段话
      ↓ 要求 AI 标注 [来源: chunk_id]
    ↓
    _get_gateway() → LocalModelGateway
    ↓
    gateway.chat(prompt)
      ↓ 模拟 AI 处理（sleep 0.5秒）
      ↓ 返回模拟分析结果
  ↓
⑥ **更新为 completed**：
    record.status = "completed"
    record.result_summary = result   ← AI 的分析结果
    db.commit()
    db.refresh(record)
  ↓
⑦ 关闭数据库连接：
    db.close()

  ═══════════════════════════════════════
  （第3阶段：查询结果 — 客户端轮询）
  ═══════════════════════════════════════

客户端 GET /tasks/5
  ↓
API → get_task(task_id=5)
  ↓
service → get_task_service(db, task_id=5, user_id=1)
  ↓
repository → get_task_by_id(db, task_id=5, user_id=1)
    ↓ SELECT * FROM analysis_tasks WHERE id=5 AND user_id=1
  ↓
API 用 TaskOut 序列化
  ↓
返回：{"id": 5, "status": "completed", "result_summary": "分析结果...", ...}
```

---

## 四、核心数据流图（文字版）

```
                  ┌───────────────┐
                  │   客户端      │
                  └──────┬───────┘
                         │ POST /tasks {"question":"..."}
                         │ X-API-Key: xxx
                         ▼
                  ┌───────────────┐
                  │   中间件      │ 生成 Request ID
                  │   middleware  │ 记录开始时间
                  └──────┬───────┘
                         ▼
                  ┌───────────────┐
                  │ Pydantic 校验  │ TaskCreate(question=str)
                  └──────┬───────┘
                         ▼
                  ┌───────────────┐
                  │ API tasks.py  │ create_task()
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │ Service  │  │ 数据库   │  │ Celery       │
   │ task_    │─▶│ commit() │  │ .delay()     │─▶ Redis
   │ service  │  │ refresh  │  │              │
   └──────────┘  └──────────┘  └──────────────┘
          │                                    │
          ▼                                    ▼
   返回客户端                              Celery Worker
   {"id":5,                                process_analysis_task()
    "status":"queued"}                        │
                                              │
                    ┌─────────────────────────┼──────────┐
                    │                         │          │
                    ▼                         ▼          ▼
             ┌────────────┐          ┌────────────┐ ┌──────────┐
             │ 数据库     │          │ Embedding  │ │ Model    │
             │ status=    │          │ Provider   │ │ Gateway  │
             │ running    │          │ →向量      │ │ →AI回答  │
             └────────────┘          └────────────┘ └──────────┘
                    │                         │          │
                    └─────────────────────────┼──────────┘
                                              │
                                              ▼
                                     ┌──────────────┐
                                     │ 数据库       │
                                     │ status=      │
                                     │ completed    │
                                     │ result_      │
                                     │ summary      │
                                     └──────────────┘
                                              │
                                              ▼
                                    客户端 GET /tasks/5
                                    → 看到完整结果
```

---

## 五、分层职责总结

| 层 | 目录 | 职责 | 不能做的事 |
|---|---|---|---|
| **API** | api/*.py | 接收 HTTP 请求、参数校验、路由匹配、返回响应 | 不能直接操作数据库 |
| **Service** | services/*.py | 组织业务逻辑（先 A 后 B 再 C） | 不感知 HTTP、不直接写 SQL |
| **Repository** | repositories/*.py | 数据库增删改查 | 不处理业务逻辑 |
| **Model** | models/*.py | ORM 表映射 | 不包含业务代码 |
| **Core** | core/*.py | 配置、日志、中间件、通用工具 | 不包含具体业务 |

---

## 六、异常处理流程

任何请求如果出现异常，处理路径如下：

```
API 函数中抛出异常
  ↓
同一层级的 try/except 捕获（如 document.py 中的各种异常）
  ↓
如果没有捕获 → 抛给 FastAPI 框架
  ↓
全局异常处理器（exceptions.py）：
  • HTTPException → http_exception_handler → 404/503 等
  • RequestValidationError → request_validation_handler → 422
  • Exception → unhandled_exception_handler → 500
  ↓
所有响应都带 X-Request-ID 响应头
```

只要任何一层出现未捕获的异常，最终都会被全局异常处理器捕获，返回统一的 JSON 错误格式，不会暴露内部 Traceback。
