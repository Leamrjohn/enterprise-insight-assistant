# Knowledge 和 RAG 实现设计

**状态：** 设计稿，未实现。文中代码和 SQL 是草案。对应总计划工单 B6、B7、B8。

**不变的约束：** 文档范围随任务冻结；检索限定当前公司；文档是不可信内容；文件上传入口保持冻结（不新增入口）。

---

## 1. 现在怎么运行

```text
入库     documents/tasks.py:14  切分 → 向量化 → 写 document_chunks（段落和 passage 都写）
检索     knowledge/tool.py:113  retrieve_evidence：向量 + jieba 关键词，RRF 合并
过滤     rag/retrieval.py       公司、文档范围、有效期（validity）
重排     tool.py:158            cross-encoder 取前 N；keep_relevant 去掉低分
充分性   tool.py:198            check_sufficiency
提示词   rag/engine.py:51       拼证据，3000 字上限
回答     knowledge/agent.py:146 模型 + 引用校验
支持检查 rag/support.py:176     逐句判断，代码再查引用和有效期
```

**要保留的好设计：** 混合检索和 RRF；有效期和文档版本过滤（旧版本进前 3 从 12/12 降到 0/12【记录】）；检索失败时可降级（`tool.py:177`）；代码复查模型的引用；反馈不混入检索文本（`agent.py:101`）。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| 向量模型只读前 128 token | 【记录】`paraphrase-multilingual-MiniLM-L12-v2` | 长片段后面的内容不影响向量 |
| 线上切分对中文基本不起作用 | 【记录】154 篇切出 154 段 | 带前言的文档 Hit@3 从 0.922 掉到 0.688 |
| 切换 `passage_v1` 两次未过验收 | `docs/worklog.md` | 仍用旧策略；检索层更好，但端到端没过 |
| 策略没有随任务冻结 | `settings.py:110` | 改配置影响进行中的任务 |
| 已确认事实混进检索词 | `knowledge/schemas.py:11` | 检索词变长，且会被 128 token 截断 |
| 无精确实体过滤 | 【记录】SUP-012 这类题靠运气 | 编号不同的文档可能混淆 |
| 未见向量索引 | 迁移和代码中搜不到 `hnsw`、`ivfflat` | 文档多了会变慢（当前语料小） |
| 提示词证据超限就停止 | `engine.py:75` | 排后面的证据进不去 |
| 评测样本小 | 45～64 题 | 很难判断小幅差异 |
| 失败无错误码 | `tool.py:265`、`:275` | 见工具平台设计 T2 |

---

## 2. 目标检索流水线

```text
1 查询理解    检索词（去掉事实）+ 实体和编号 + 有效期窗口
2 候选召回    向量 Top K + 关键词 Top K + 精确实体命中
3 融合        RRF；精确实体命中加权
4 重排        cross-encoder
5 过滤        低分、过期、无权限（再检查一次）
6 扩展        相邻片段、表头（有预算才加）
7 充分性      有没有足够证据
8 上下文      交给上下文引擎（设计 02）
```

### 2.1 查询理解

| 现在 | 目标 |
|---|---|
| `render_query()` 把事实拼进检索词 | **检索词只用 `resolved_question`**；事实只用于回答阶段 |
| 实体隐含在文本里 | 从 `QuestionFacts` 取实体和编号，作为显式过滤条件 |

```python
@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    identifiers: tuple[str, ...]     # SUP-003、CUST-0280
    validity: ValidityWindow
    document_ids: tuple[int, ...]
```

**先验证再改：** 去掉事实后对混合题的影响未知，要用评测确认。

### 2.2 精确实体

切分时已经抽取了编号（`document_chunk.py:155` 的 `_IDENTIFIER`）。把它存成字段：

```sql
ALTER TABLE document_chunks ADD COLUMN identifiers text[] NOT NULL DEFAULT '{}';
CREATE INDEX ix_document_chunks_identifiers ON document_chunks USING gin (identifiers);
```

| 情况 | 行为 |
|---|---|
| 问题有编号，有片段命中 | 命中片段进入候选并加权 |
| 问题有编号，无片段命中 | 其余候选降权；提示“未找到该编号的资料”，**不把别的编号当答案** |
| 问题无编号 | 不受影响 |

**这是加权，不是强制过滤：** 否则文档正文写全称而问题写简称时会漏。

### 2.3 向量模型升级（B7，**需批准：新模型**）

| 选项 | 优点 | 代价 |
|---|---|---|
| 换支持更长文本的中文模型（候选如 BGE 系列） | 长片段质量更好 | 列维度变化，要重算向量；镜像和内存变大；延迟变化 |
| 保持现有模型 + 短片段（`passage_v1` 约 160 字） | 不用重算；已基本避开 128 token 限制 | 模型本身不是中文专用 |

**建议先用第二项完成切换，再用评测判断是否值得换模型。** 候选模型的具体规格和效果开工时要实际测试，不能只看介绍。

**如果要换，双写迁移：**

```sql
ALTER TABLE document_chunks
  ADD COLUMN embedding_v2 vector(<维度>),
  ADD COLUMN embedding_v2_model varchar(128);
```

```text
1 后台分批回填 embedding_v2（可中断、可重复）
2 影子：同一查询两种向量都检索，比较结果
3 按公司切换
4 稳定后删除旧列（需批准）
```

### 2.4 向量索引

**先测量：** 用 1 万、10 万片段压测检索耗时。当前语料很小，顺序扫描没有问题。

超过阈值时加 HNSW：

```sql
CREATE INDEX CONCURRENTLY ix_document_chunks_embedding
  ON document_chunks USING hnsw (embedding vector_cosine_ops);
```

**多租户注意：** 带公司过滤时，HNSW 可能先找到别家的近邻再过滤，结果变少。要测试召回率，必要时调大 `hnsw.ef_search` 或按公司分区。**隔离由 RLS 保证，不受索引影响。**

### 2.5 相邻片段扩展

短片段的代价是上下文被切开。重排后，如果预算有余，加入同文档的前后片段，并标记 `expanded_from`。**扩展片段可以引用，但有效期和权限要相同；** 进入上下文时优先级低于重排命中。

---

## 3. 切换 `passage_v1` 的具体计划（B6）

**过去两次失败的教训：** 同时改了切分和 10/3 → 30/5，失败时分不清原因；每轮样本太少；端到端的问题有一部分来自后面的复核（证据题“限定被丢弃”，`docs/worklog.md`）。

**新的切换步骤，每次只改一个变量：**

| 步 | 改动 | 判断依据 |
|---|---|---|
| 0 | 先修限定条件（设计 12 的 B5） | 否则端到端结果受它干扰 |
| 1 | 策略随任务冻结，可按公司选择 | 不影响线上行为 |
| 2 | 只换切分，保持 10/3 | 检索指标 + Knowledge 评测 |
| 3 | 切分固定，10/3 → 30/3 | 看召回提升和耗时 |
| 4 | 30/3 → 30/5 | 看答案进提示词率、token |
| 5 | 选定配置连跑冒烟 ≥ 5 轮 | 和旧策略按题比较 |

**每一步的通过线（比较同一批题，同一提交）：**

| 指标 | 要求 |
|---|---|
| 陷阱题（旧版本排除） | 12/12 |
| 答案进入提示词 | 不低于当前 |
| 留出集 | 不低于当前 |
| Knowledge 正确 | 不低于 49/57，目标 ≥ 52/57 |
| 冒烟 | 每题按错误率比较，不只看总数 |
| 耗时、token | 在预算内 |

**样本量要诚实：** 目前旧策略 9 次错 1 次，新策略 4 次错 2 次，不足以下结论【记录】。证据题要专门重复足够次数（比如各 25 次），先算费用并批准。

**策略冻结：**

```text
建任务 → EffectivePolicy.rag = {policy_id, retrieval_top_k, rerank_top_k, min_scores}
       → 写入任务快照
RAGTool 从快照读，不读 get_settings()
```

---

## 4. 文档治理（B8）

| 能力 | 现状 | 目标 |
|---|---|---|
| 版本 | 有 `version_group`、`superseded_by`（`documents/models.py:33-37`） | 保留；增加回归测试 |
| 有效期 | 有 `effective_from/to`、`applies_to` | 保留 |
| 查看权限 | `min_view_role`，工具层校验 | 检索 SQL 也带上，形成双层 |
| 重新处理 | `backfill_passage_chunks.py` | 通用的“重新切分和向量化”任务，记录处理版本 |
| 删除 | 需要确认向量和片段一起删除 | 删除联动片段、记忆标记（见记忆设计） |
| 文档内注入 | 有“不可信”声明 | 上下文定界符；注入集测试 |
| 解析质量 | 表格、页眉页脚影响切分 | 增加解析评测；问题记录到清单 |

**文档处理版本：**

```sql
ALTER TABLE documents
  ADD COLUMN chunking_version varchar(32),
  ADD COLUMN embedding_model varchar(128),
  ADD COLUMN processed_at timestamptz;
```

`document_chunks` 已有切分策略字段，可以据此重新处理单篇文档，不影响其他文档。

**上传入口保持冻结：** 这里只处理已有文档和后台重处理，不扩大上传能力。

---

## 5. 一次检索的具体过程

“哪些资料支持 SUP-003 传感器批次异常？”

```text
查询理解  text=问题；identifiers=[SUP-003]；有效期=今天；文档范围=任务冻结的 42 篇
召回      向量 30 + 关键词 30 + 编号命中 4
融合      RRF，编号命中加权 → 30 条
重排      cross-encoder → 前 5，分数 0.97/0.91/0.88/0.62/0.31
过滤      min_score=0.5 → 剩 4 条；复查有效期和权限
扩展      有预算，加入 1 个相邻片段
充分性    通过
上下文    Knowledge 策略 4000 token，全部保留
回答      模型给答案和 chunk_id
支持检查  逐句判断；代码确认引用来自本次检索且有效
证据      带 retrieval_policy_id、chunking_version
```

**编号不存在时：** 比如 SUP-999，没有片段命中，返回 `insufficient_evidence`，提示资料中没有该编号。

---

## 6. 失败路径

| 场景 | 系统行为 |
|---|---|
| 嵌入模型失败 | 只用关键词召回，标记 `degraded`，报告注明 |
| 重排失败 | 用检索顺序（现有降级），标记 `degraded` |
| 向量和关键词都失败 | `infra_error`，重试后明确失败 |
| 数据库超时 | 现有 `statement_timeout`，归 INFRA |
| 证据不足 | `insufficient_evidence`，不让模型硬答 |
| 全部证据超预算 | 上下文引擎压缩；仍不够时明确说明 |
| 回填中断 | 按主键断点继续；可重复执行 |
| 一个向量列迁移一半 | 按文档记录版本，未迁移的走旧向量或暂不进新策略 |

**降级不能跳过校验，** 这是已确认的边界。

---

## 7. 配置

| 配置项 | 默认值 |
|---|---|
| `RAG_RETRIEVAL_POLICY` | 现值，写入快照 |
| `RAG_RETRIEVAL_TOP_K` / `RAG_RERANK_TOP_K` | 10 / 3（现值） |
| `RAG_RRF_K` | 60 |
| `RAG_IDENTIFIER_BOOST` | 用评测确定 |
| `RAG_NEIGHBOR_EXPANSION` | `false` |
| `RAG_QUERY_INCLUDE_FACTS` | `true`（现状），改动后切 `false` |
| `RAG_DEGRADE_ON_RERANK_FAILURE` | `false`（现状主链） |

---

## 8. 落地步骤

**验证命令是计划，尚未运行。** 检索评测免费（本地模型）；端到端要花钱，要先批准。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B6a 策略冻结** | 快照、`knowledge/tool.py` | 运行中改配置不影响任务；检索结果不变 | revert |
| **B6b 检索诊断** | 记录每步候选数量和分数（不含正文） | 任一任务能回答“为什么没找到” | 不影响业务 |
| **B6c 检索词去事实** | `knowledge/schemas.py`、开关 | 混合题评测不降 | 开关 |
| **B6d 精确实体** | 迁移、回填、检索融合 | `se-012` 等错题改善；陷阱题 12/12 | 开关 |
| **B6e 切换切分** | 第 3 节步骤 2 | 通过线 | 策略切回 |
| **B6f 调候选数** | 第 3 节步骤 3、4 | 通过线 | 策略切回 |
| **B6g 相邻扩展** | 检索和上下文 | 答案进提示词率提升；token 可控 | 开关 |
| **B7 模型评估**（**需批准**） | 候选模型离线对比 | 明显胜出才迁移 | 不迁移 |
| **B8a 文档治理** | 权限双层、处理版本、重处理任务 | 权限和版本回归；跨公司 0 | revert |
| **B8b 性能** | 压测，必要时加索引 | 给定规模下 P95 达标 | 删除索引 |

---

## 9. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 文档前加 1500 字前言 | Hit@3 不再大幅下降 |
| 问不存在的编号 | 说明没有，不答别的编号 |
| 旧版本文档 | 陷阱题 12/12 |
| 运行中切换策略 | 进行中的任务不变 |
| 重排失败 | 报告注明降级 |
| 任一 Knowledge 结果 | 可查策略、切分版本和每步候选数 |
| 端到端 | Knowledge ≥ 52/57，留出集不落后 |

**52/57 是目标，不是保证。** 留出集只有约 15 题且被看过多次【记录】，所以评测设计要先扩充（见设计 13）。

**仍需开工时确认：** 模型参数的具体规格；`rag/retrieval.py` 融合内部逻辑是否便于加权；`passage_v1` 片段的 identifiers 是否已存在正文前缀；`effective_*` 对历史文档的覆盖率。
