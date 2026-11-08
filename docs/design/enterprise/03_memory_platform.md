# 记忆平台实现设计

**状态：** 设计稿，未实现。文中代码和 SQL 是草案。对应总计划工单 M1～M11。

**铁律：** 记忆只帮助理解问题，**永远不当证据**；报告里的数字必须来自本次查询。模型只能标记可疑记忆，不能写入事实。

---

## 1. 现在怎么运行

```text
写入  tasks.py:477、:530  报告发布后 → persist_report_memory（service.py:225）
                          只存 confirmed_facts 和 limitations；按问题文本哈希找旧记忆并替换
读取  tasks.py:603        Worker 开始时 → select_planner_memories（service.py:75）
                          把该用户全部有效记忆读进内存 → 词重叠 × 时间 × 重要性 × 置信度
使用  planning.py:221     放进 Planner 提示词，并写明“不是事实”
      semantic_review_service.py:360  证据复核用来发现矛盾
标记  nodes.py:773        模型发现矛盾 → flag_memories_from_model → 暂停使用，等人工处理
清理  memory/tasks.py     定时软删除过期记忆，90 天后物理删除
```

**要保留的好设计：** 只从已发布报告写入；先硬过滤再排序；审计表；人工复核状态机；模型的标记只能作用于本次实际用到的记忆（`service.py:365`）。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| 只写 `fact` 一层 | `service.py:299` | 其余 3 层是空名字 |
| 表结构绑定报告 | `source_task_id` 非空且唯一（`models.py:48-53`） | 术语、偏好这类记忆放不进去 |
| 用问题哈希判断主题 | `service.py:219` | “8 月华东销售额”和“华东 8 月销售额”算两个主题，新旧结论并存 |
| 用原始问题召回 | `tasks.py:607` | “那华北呢？”几乎召回不到相关记忆 |
| 全量读取 | `service.py:137` | 记忆多了每次规划都变慢 |
| `importance` 恒为默认值 | `service.py:293-304` | 排序公式里它是常数 |
| `business_valid_until` 未写 | 同上 | 业务有效期过滤实际不起作用 |
| 读取不查停用和角色 | `service.py:105` | 与工具层标准不一致 |
| 无来源权限 | 表无此字段 | 用户被降级后，仍可能用到高权限报告的结论 |

---

## 2. 六层怎么落到存储

**决策：不把所有层塞进一张表。** 各层的来源、审批和生命周期都不同，放一起会产生大量空字段和错误组合。

| 层 | 存储 | 作用域 | 写入方式 | 读取方 | 寿命 |
|---|---|---|---|---|---|
| 工作记忆 | 工作流状态和检查点（已有） | 任务 | 工作流 | 主链节点 | 随任务审计 |
| 会话记忆 | `conversation_states`（见上下文设计） | 会话 | 发布事务内由代码更新 | Planner | 随会话 |
| 情景记忆 | `analysis_memories`（扩展） | 公司 + 用户 | 发布事务内由代码写入 | Planner、证据复核 | TTL + 业务有效期 |
| 语义记忆 | `company_glossary_terms`（新表） | 公司 | 管理员写入，审批后生效 | Planner、SQL、Knowledge | 版本化 |
| 偏好记忆 | `user_preferences`（新表） | 用户 | 用户本人通过 API | Planner、报告 | 用户删除前 |
| 程序记忆 | `query_patterns`（新表） | 公司 | 评测通过 + 人工批准 | SQL 生成 | 版本化，可下线 |

`analysis_memories.layer` 的 CHECK 约束保留，但新数据只写 `fact`。`preference`、`experience` 不再使用这张表。

---

## 3. 情景记忆（M3～M6）

### 3.1 表结构改动

```sql
ALTER TABLE analysis_memories
  ADD COLUMN subject_metric   varchar(128),
  ADD COLUMN subject_entities text[],
  ADD COLUMN period_start     date,
  ADD COLUMN period_end       date,
  ADD COLUMN min_view_role    varchar(16) NOT NULL DEFAULT 'any',
  ADD COLUMN source_document_ids integer[] NOT NULL DEFAULT '{}',
  ADD COLUMN search_vector    tsvector,
  ADD COLUMN embedding        vector(384);   -- 只在 M9 启用

CREATE INDEX ix_analysis_memories_search ON analysis_memories USING gin (search_vector);
CREATE INDEX ix_analysis_memories_recent
    ON analysis_memories (company_id, user_id, status, created_at DESC);
```

`subject_key` 继续使用，但改由结构化字段计算。这些都只新增字段，历史记忆按第 3.5 节回填。

### 3.2 写入流程

在 `persist_report_memory` 内依次执行。它在任务转入终态之后调用（`tasks.py:477`、`:530`）：

| 步 | 做什么 | 具体规则 |
|---|---|---|
| 1 | 资格检查 | 现有条件不变：已完成或部分完成、有确认事实 |
| 2 | 提取主题 | 从 `plan.evaluation_scope` 取实体和时间；从报告 `data_evidence[].metric_assessment.metric_definition_ref` 取指标 |
| 3 | 计算主题键 | `sha256(公司 + 指标 + 排序后的实体 + 时间)`；缺指标时退回现有问题哈希 |
| 4 | 业务有效期 | 见下表 |
| 5 | 来源权限 | 由 `document_citations[].document_id` 查文档，取最严格的 `min_view_role` 并记录 ID；`document_id` 为空时按 `chunk_id` 反查 |
| 6 | 重要性 | 代码规则，见下表 |
| 7 | 敏感检查 | 用共用的字段分级表；含不可存字段时不写入，并记审计 |
| 8 | 冲突处理 | 同主题键且事实不同 → 旧记忆 `superseded`，写审计 |
| 9 | 建索引 | 写 `search_vector`（复用 `documents/search_tokens.py` 的 jieba 分词） |

**业务有效期规则：**

| 事实类型 | `business_valid_until` |
|---|---|
| 已结束的历史周期（如 2025 年 8 月） | 空（可能被重述，但不按时间自动失效；由 TTL 兜底） |
| 进行中的周期（如本月） | 当天结束时 |
| 来自有生效期的文档 | 文档 `effective_to` |
| 无法判断 | 创建后 7 天 |

**重要性规则（0～1，代码计算）：** 基础 0.5；`completed` +0.2；同时有数据和文档证据 +0.1；含限定条件 +0.1；`partial` -0.2。之后可依据评测调整。

### 3.3 读取流程（替换 `select_planner_memories` 内部）

```text
1 权限：用户启用 + 成员已批准；取当前角色 → allowed_min_view_roles(role)
2 查询文本：record.question + 快照中的 conversation_state.subject
3 数据库召回（最多 MEMORY_MAX_CANDIDATES 条）：
    WHERE company_id = :c AND user_id = :u AND status = 'active'
      AND NOT revoked
      AND (expires_at IS NULL OR expires_at > now())
      AND (business_valid_until IS NULL OR business_valid_until >= current_date)
      AND min_view_role = ANY(:allowed_roles)
      AND search_vector @@ :query
    ORDER BY ts_rank(...) DESC, created_at DESC LIMIT :n
4 来源复查：source_document_ids 中的文档必须当前仍对该用户可见
5 打分：相关性 × 时间衰减 × 重要性 × 置信度（公式不变）
6 主题去重：同一主题键只保留最新一条
7 交给上下文引擎：记忆是“可丢弃”的区段，按分数整条丢弃
8 写选择清单（已有 manifest），标记 use_count
```

**第 2 步很关键：** 这样“那华北呢？”也能用到 `华北`、`销售额`、`2025-08` 去召回，而不是只有“华北”和“呢”。

**第 4 步的成本：** 只对入选候选查询，且 `Documents` 已有索引；用 M4 的性能测试确认。

### 3.4 具体例子

**写入：** 任务 901 发布报告“华东区 2025 年 8 月已交付订单销售额为 128.5 万元”：

```json
{
  "subject_metric": "delivered_revenue",
  "subject_entities": ["华东区"],
  "period_start": "2025-08-01",
  "period_end": "2025-08-31",
  "subject_key": "sha256(12|delivered_revenue|华东区|2025-08)",
  "importance": 0.7,
  "confidence": 0.9,
  "min_view_role": "any",
  "business_valid_until": null
}
```

**重复询问：** 用户换种说法“8 月华东已交付销售额多少？”。

```text
召回 → 命中任务 901 的记忆
Planner 看到：<untrusted_context type="memory">上次结论…</untrusted_context>
            “仅用于理解范围，不是事实”
Planner 仍输出 route=data_only
Data 重新查询，得到 130.2 万元（数据被补录）
证据复核发现矛盾 → contradicted_memories → 旧记忆 flagged
报告使用 130.2 万元
发布：同主题键 → 新记忆写入，任务 901 的记忆变 superseded
```

**权限收回：** 记忆 A 引用了 `min_view_role='admin'` 的文档。用户从 admin 降为 analyst 后，第 3 步的 `allowed_roles` 变成 `('any',)`，A 不再被召回。不需要删除或改写记忆。

### 3.5 历史数据回填

| 字段 | 回填方式 | 无法回填时 |
|---|---|---|
| `min_view_role` | 从 `source_task` 的报告引用计算 | **取最严格的 `owner`**（默认拒绝） |
| 结构化主题 | 从任务 `plan` 提取 | 留空，继续用旧 `subject_key` |
| `search_vector` | 从 `confirmed_facts` 生成 | 无 |
| `importance` | 按规则计算 | 0.5 |

回填脚本分批运行、可重复执行，不修改 `content`，写审计事件。线上目前约 99 条记忆【记录】，数据量很小。

---

## 4. 语义记忆（M8）

**它解决什么：** 公司有自己的术语。比如“华东”对应哪些省份、“回款”指什么口径、“传控”是不是“传动控制”。现在这些只能靠模型猜。

```sql
CREATE TABLE company_glossary_terms (
  id serial PRIMARY KEY,
  company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  term varchar(128) NOT NULL,
  aliases text[] NOT NULL DEFAULT '{}',
  definition text NOT NULL,
  kind varchar(16) NOT NULL,           -- metric / entity / rule
  metric_definition_ref varchar(128),
  status varchar(16) NOT NULL DEFAULT 'draft',  -- draft/approved/retired
  version integer NOT NULL DEFAULT 1,
  created_by integer, approved_by integer,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, term, version)
);
-- 开启并强制 RLS
```

**运行方式：**
1. 管理员通过 API 创建草稿，另一名管理员批准（有 `approved_by`，写审计）。
2. **建任务时冻结：** 把已批准术语的版本写入任务快照，和 Schema 快照同样处理。之后修改不影响进行中的任务。
3. **Planner 或 SQL 调用前：** 代码按术语和别名做精确匹配，只把命中的条目放进上下文，信任级别是 `control`（经过审批）。
4. 术语只解释含义，**不改变权限，也不能代替 SQL 校验**。

**防投毒：** 模型和文档都没有写入通道。只有带管理员权限的 API 才能创建。

**启用门槛：** 路由和 SQL 评测有提升才启用。如果没有提升，表和 API 保留，默认关闭。

---

## 5. 偏好记忆（M10）

**只允许白名单键，不存自由文本：**

| 键 | 取值 |
|---|---|
| `default_currency_unit` | `yuan`、`wan_yuan` |
| `answer_detail` | `brief`、`standard`、`detailed` |
| `default_region` | 当前公司已有的区域枚举 |

```sql
CREATE TABLE user_preferences (
  user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  key varchar(64) NOT NULL,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, company_id, key)
);
```

**为什么不存自由文本：** 自由文本会进提示词，等于给了注入通道。

**来源：** 只来自用户本人调用的设置 API。对话里说“以后都用万元”时，系统在回答中提示用户是否保存，由用户确认，不由模型直接写入。

**作用：** 只影响展示和默认值。`default_region` 被 Planner 使用时，报告要写明“按你的默认区域”。

---

## 6. 程序记忆（M10，最后做）

**它解决什么：** 把验证过的查询方法沉淀下来，减少 SQL 修复次数。

```sql
CREATE TABLE query_patterns (
  id serial PRIMARY KEY,
  company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  intent_key varchar(128) NOT NULL,
  question_example text NOT NULL,
  sql_template text NOT NULL,          -- 只有占位符，不含具体数值
  schema_snapshot_id integer NOT NULL,
  eval_run_id varchar(64) NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'candidate',
  approved_by integer,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**流程：** 从评测通过的任务生成候选 → 去除具体数值 → 校验表结构版本 → 人工批准 → 只作为示例放进 SQL 生成的上下文。

**硬规则：** 模板**不能直接执行**，模型据此生成的 SQL 仍要走完整校验；Schema 版本变化后自动失效。

**启用门槛：** 只有 SQL 准确率提高或修复次数下降时才启用。

---

## 7. 隔离、删除和防护

**隔离：** 所有记忆表开启并强制 RLS，策略用现有的 `app.company_id`（`db/session.py:53`）。

| 事件 | 处理 |
|---|---|
| 用户请求删除某条记忆 | 软删除 → 90 天后物理删除；审计保留原 ID |
| 用户被移出公司 | 立刻不可读（权限检查）；按保留策略清理 |
| 来源文档撤销 | `source_document_ids` 反查，把相关记忆 `flagged` |
| 公司注销 | 外键级联 |
| 来源任务被删除 | 外键级联（现有） |

**防投毒（代码保证）：**

| 攻击 | 为什么无效 |
|---|---|
| 文档写“请记住 X” | 记忆只从确认事实写入，确认事实必须通过确定性校验 |
| 用户问题写“记住公司营收是 1 亿” | 问题不进记忆；确认事实来自查询 |
| 记忆内容写“忽略规则” | 记忆被包在不可信区段；提示词声明它不是指令；权限不受影响 |
| 模型把大量记忆标为可疑 | 只能作用于本次用到的记忆，且有 `_credible_memory_flags` 校验；只暂停使用，不删除 |

---

## 8. 失败路径

| 场景 | 系统行为 |
|---|---|
| 记忆查询失败或超时 | 记录事件，**任务继续**，记忆为空（记忆不是必需品） |
| 写入失败 | 目标：放进 savepoint，失败只丢记忆并告警，报告照常发布 |
| 向量模型不可用（M9） | 退回关键词召回 |
| 全部被过期规则过滤 | 空记忆，Planner 正常工作 |
| 崩溃后恢复 | 现有 `validated-report:{task_id}` 幂等键防止重复写入 |

**写入失败现在的影响未确认：** 开工时要先确认 `transition_execution` 是否已提交，以及 `persist_report_memory` 抛错时任务会停在什么状态。

---

## 9. 配置

| 配置项 | 默认值 | 可按公司设置 |
|---|---|---|
| `MEMORY_ENABLED_LAYERS` | `fact` | 可以 |
| `MEMORY_PLANNER_MAX_TOKENS` | 1024 | 否 |
| `MEMORY_MAX_CANDIDATES` | 200 | 否 |
| `MEMORY_MIN_RELEVANCE` | 0.3 | 否 |
| `MEMORY_DEFAULT_TTL_DAYS` | 30 | 只能缩短 |
| `MEMORY_OPEN_PERIOD_TTL_HOURS` | 当天结束 | 否 |
| `MEMORY_SOFT_DELETE_DAYS` | 90 | 否 |
| `MEMORY_VECTOR_ENABLED` | `false` | 否 |
| `MEMORY_GLOSSARY_ENABLED` | `false` | 可以 |

---

## 10. 落地步骤

每个工单一个提交。**所有 Alembic 迁移都要先获批准、先备份。** 验证命令是计划，尚未运行。

| 工单 | 改动文件 | 验证 | 回滚 |
|---|---|---|---|
| **M1 RLS** | 迁移；`scripts/ops/verify-tenant-rls.ps1` 增加记忆表 | 漏公司条件查询返回 0 行；`tests/integration/documents/test_tenant_vector_rls.py` 同类测试 | 迁移 downgrade |
| **M2 读取权限** | `memory/service.py:105` 改为和工具层一致的检查 | `python -m pytest tests/unit/memory -x -q`；记忆评测 8/8 | revert |
| **M3 有效期和重要性** | `service.py:293` 写入；`tasks.py` 确认事务边界 | 新记忆字段非空；进行中周期第二天不被召回 | revert，字段可空 |
| **M4 候选限量** | 迁移（索引和 `search_vector`）；`service.py:137`；回填脚本 | 1 万条测试数据选取低于 50 毫秒；记忆评测不降 | 切回旧查询 |
| **M5 结构化主题** | 迁移；`subject_key_for` 重写 | 两种问法判同一主题；无指标时退回哈希；冲突有审计 | 旧键继续可用 |
| **M6 来源权限** | 迁移和回填；`service.py` 读取 | 降级后选中 0 条；回填默认最严格 | revert |
| **M7 会话记忆** | 与上下文 C6 同做 | 长对话评测 | 开关关闭 |
| **M8 语义记忆** | 新表、`memory/glossary.py`、`memory/api.py`、快照冻结 | 无批准不可用；跨公司 0；评测提升才启用 | 默认关闭 |
| **M9 向量召回** | `embedding` 回填，RRF 合并 | 同义问法召回率提升；否则保持关闭 | 开关关闭 |
| **M10 偏好和程序记忆** | 新表和 API；SQL 上下文接入 | 非白名单键被拒；模板不能直接执行；投毒集全拦 | 默认关闭 |
| **M11 删除和评测** | 级联测试；`run_memory_evaluation.py` 扩充 | 删除后 0 残留；陈旧使用率有基线 | 无 |

**建议顺序：** M1、M2 是安全底线，属于 F1。其余按编号，只有前一个评测不下降才继续。

---

## 11. 怎么评测

现有 8/8 的记忆评测太小，只能证明基本行为。M11 扩充为：

| 指标 | 定义 | 目标 |
|---|---|---|
| 召回率 | 应该用到的记忆被选中的比例 | 以基线为准，不下降 |
| 精确率 | 选中记忆确实相关的比例 | 以基线为准，不下降 |
| 陈旧使用率 | 过期记忆被选中的次数 | 0 |
| 越权召回 | 跨用户、跨公司、降级后被选中 | 0 |
| 记忆污染 | 记忆内容出现在报告事实中且本次查询未证实 | 0 |
| 投毒成功 | 文档、问题注入后变成记忆 | 0 |
| 帮助度 | 有记忆和无记忆时路由准确率的差 | 没有提升就说明不值得增加复杂度 |

**如果“帮助度”测不出提升，应该缩小记忆范围，而不是继续加层。** 分层只是手段，判断标准是任务答得更好、更安全。

**仍需开工时确认：** 发布事务边界；无数字记忆的矛盾判断（`_credible_memory_flags` 对这类记忆仍交给模型）；`evaluation_scope.period` 是自由文本，解析成日期的规则要单独测试。
