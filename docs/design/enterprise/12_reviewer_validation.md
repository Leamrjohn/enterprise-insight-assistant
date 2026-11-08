# Reviewer 和确定性校验实现设计

**状态：** 设计稿，未实现。文中代码是草案。对应总计划工单 B5、B9、B10。

**不变的约束：** 能否发布由确定性校验决定，Reviewer 不能替代它；报告数字必须来自本次查询；放宽校验规则要先批准。

---

## 1. 现在怎么运行

```text
reviewer_node        nodes.py 约 :812
compose_report       composer.py  代码组装报告
build_confirmed_facts metrics/facts.py:63  无模型：把结果行渲染成事实（前 5 行）
证据语义复核          semantic_review_service.py:349  模型判断 supported/partial/unsupported
限定条件              reviewer_agent.py:191  只保留文档中逐字存在的句子
最终校验              reviewer_agent.py:74
    validate_schema、validate_numbers、citation_validator；coverage 只做诊断
smart_router          router.py:54  引用失败停止；数字或结构失败重规划
保存前校验            tasks.py:380 附近的 validate_report
发布决定              lifecycle/publication.py:35 decide_completion
人工审核              reviews/service.py:24 有因果假设就要审核
```

**要保留的好设计：**
- 确认事实由代码生成，模型不能编造（`facts.py:64`）。
- 引用校验检查归属和本次范围。
- 限定条件要求逐字存在（这条规则是对的）。
- 校验失败时用安全文本，不暴露模型内容（`reviewer_agent.py:128`）。
- 是否需要人工审核由代码决定（`reviews/service.py:24`）。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| **数字只查“证据里有没有”** | `numeric_validation.py:87-108` 把所有查询行和文档片段的数字合成一个集合 | 把华东的 128.5 说成华北的，校验也能通过 |
| 限定条件被模型改写后丢弃 | `reviewer_agent.py:212`；【记录】任务 518、578 | 约 1/10 的证据题缺限定，冒烟不稳定 |
| 复核结果不留存 | 【记录】任务 488 | 无法解释为什么重规划 |
| 终态规则分散 | `publication.py:35`、`router.py`、节点；预算耗尽可能标 `partial`【记录】 | “部分完成”的含义不一致 |
| 只留 5 行事实 | `facts.py` 的 `rows[:5]` | 多行结果的后面部分不进入事实 |
| `coverage_valid` 恒为 True | `reviewer_agent.py:111` | 这是有意的诊断项，但字段名容易误导 |
| `reviewer_agent.py` 711 行 | | 难改、难审 |

---

## 2. 修复限定条件（B5）

**这是当前最上游的已知失败。** 另一个会话已确认原因：模型把限定条件改写了，被逐字校验丢弃。

**不放宽校验。** 改成不让模型自己写原文：

### 2.1 让模型选句子，不写句子

```text
1 代码把每个已引用片段切成带编号的句子（用现有切分规则）
2 提示词里提供句子清单：
    <sentences chunk_id="17">
      [17.1] 工单和退货是可复算事实，供应商批次异常是文档支持的原因假设。
      [17.2] 该复盘不是对所有产品或所有客户的质量结论。
    </sentences>
3 模型只返回句子编号：
    "document_qualification_refs": ["17.1", "17.2"]
4 代码按编号取回原文，生成 DocumentQualification
```

**效果：** 输出天然和原文一致，不存在“改写后被丢弃”。未知编号直接忽略并计数。

**这一步之后逐字校验仍保留，作为防御。** 提示词也可以减少“不得改写”这类说明。

**兼容：** 新旧字段并存一个版本。提示词变化要重新录制回放，**有费用，要批准。**

### 2.2 确认方案之前先测量

| 对照 | 指标 |
|---|---|
| 改之前：证据题重复 25 次 | 限定被保留的比例 |
| 改之后：同一题重复 25 次 | 同一指标，目标 25/25 |
| 其他题 | Knowledge 不下降；模型调用和 token 不明显增加 |

**费用：** 25 次约几美分级别（参考：冒烟每轮约 $0.025【记录】，单题更少），开跑前再按当时价格报告。

---

## 3. 数字校验升级（B9）

现在只确认“数字在证据里出现过”。目标是确认**这个数字属于这个说法**。

### 3.1 分类处理

| 文本来源 | 例子 | 校验方式 |
|---|---|---|
| 代码渲染的事实 | `confirmed_facts` | 本来就来自结果行，只校验结构 |
| 模型写的回答（文档） | `document_findings` | 数字必须在**该句引用的片段**内 |
| 模型写的摘要 | `executive_summary` | 数字必须匹配某条事实，且实体和时间相符 |
| 计算得到的数字 | 环比、占比 | 代码计算后提供；模型自算的不接受 |

### 3.2 事实绑定

给事实增加结构化字段：

```python
class ConfirmedFact(BaseModel):
    fact_id: str
    statement: str
    data_evidence_ids: list[str]
    # 新增
    values: list[FactValue] = []

class FactValue(BaseModel):
    metric_ref: str | None
    value: Decimal
    unit: str | None
    entities: dict[str, str]     # {"region": "华东"}
    period: str | None
    evidence_id: str
    row: int
    column: str
```

**摘要校验：**

```text
对摘要的每句：
  抽取数字
  抽取句子里的实体和时间（用语义层和时间解析）
  查找 FactValue：数字相同（允许显示精度舍入）
                  且 实体、时间不冲突
  找不到 → numbers_valid=false
```

**例子：**

| 摘要 | 事实 | 结果 |
|---|---|---|
| 华东 8 月销售额 128.5 万 | 华东 / 2025-08 / 128.5 万 | 通过 |
| 华北 8 月销售额 128.5 万 | 华东 / 2025-08 / 128.5 万 | **失败**（现在会通过） |
| 销售额 128.5 万 | 华东 / 2025-08 / 128.5 万 | 通过（没写实体，不冲突） |
| 环比增长 12% | 无派生值 | 失败，除非代码已提供 |

**派生指标由代码计算：** 比较类查询在 Reviewer 组装时计算差值和百分比（`Decimal`），作为 `FactValue` 提供给模型。

**上线顺序：** 新校验先走影子模式，只记录“新规则会判失败”的情况，分析是否误判；再启用。**这会让校验更严，也可能增加失败，要批准。**

### 3.3 单位

把“万”“亿”“%”做规范化。现有 `_display_matches_source` 只处理百分比。`128.5 万` 和 `1285000` 要能对应上，否则现在要么误判，要么模型被迫写长数字。

---

## 4. 语义复核的边界

| 项目 | 规则 |
|---|---|
| 作用 | 判断证据是否真正回答了问题；这是代码难以判断的部分 |
| 不能做 | 不能决定权限；不能让校验失败的内容发布 |
| 结果留存 | 写事件：结论、`supported_chunk_ids`、限定编号、是否修复；不写原文 |
| 判定波动 | 温度 0（G3）；用固定题重复测量 |
| 对结果的影响 | `partial`、`unsupported` 进入限制说明，由决策表处理 |

**留存格式：**

```json
{
  "event_type": "evidence_review_completed",
  "details": {
    "verdict": "supported",
    "supported_chunks": [17, 18],
    "qualification_refs": ["17.1", "17.2"],
    "qualifications_kept": 2,
    "contradicted_memories": 0,
    "prompt_version": "evidence@2.0.0",
    "repaired": false
  }
}
```

---

## 5. 终态规则表（B10）

**把散落的判断收成一张表，全项目只有一个定义：**

| 情况 | 任务状态 | 报告 | 用户看到 |
|---|---|---|---|
| 证据完整，校验通过，无因果假设 | `completed` | 发布 | 完整报告 |
| 含因果假设 | `awaiting_review` | 草稿 | 等待审核 |
| 混合题只有一边有证据 | `partial` | 发布 | 报告 + 明确说明缺什么 |
| 数据为空 | `partial` 或 `completed`，按现有 `no_matching_records` 规则 | 发布 | 无匹配记录 |
| 文档证据不足（纯文档题） | `partial` | 发布 | 资料不足 |
| 校验失败且重规划用完 | `partial`（有其他有效证据）或 `failed` | 安全文本 | 不发布可疑内容 |
| 引用校验失败 | `failed`（安全类） | 不发布 | 明确失败，写告警 |
| 模型预算耗尽，已有有效证据 | `partial`，限制码 `budget_exhausted` | 发布已校验部分 | 说明因预算未完成 |
| 模型预算耗尽，无证据 | `failed` | 不发布 | 明确失败 |
| 缺信息 | `needs_clarification` | 无 | 具体问题 |
| 取消 | `cancelled` | 不发布 | 已取消 |

**这张表要和现有行为逐条比较。** 上面的“预算耗尽”和“校验失败后 partial”是目标，可能和现状不同，改动时要在 PR 里列出差异并批准。

**测试：** 用表驱动，覆盖所有行。`decide_completion`（`publication.py:35`）作为唯一实现，其他地方不再自己判断。

---

## 6. 报告结构

```text
schema_version: "1.3"
新增：
  confirmed_facts[].values          结构化数字
  provenance:
    prompt_set, profile_set, retrieval_policy, semantic_model_version,
    config_snapshot_hash
  limitations[].code                固定枚举
```

- 旧版本继续可读，`Literal["1.0","1.1","1.2"]`（`schemas.py:147`）加新值。
- 前端按字段渲染，未知字段忽略。
- 报告里不暴露 `chunk_id` 给用户（【记录】回答正文偶尔出现，要由代码过滤并加校验）。

---

## 7. 文件拆分

`reviewer_agent.py` 按职责拆开，只移动不改行为：

```text
reporting/
    reviewer_agent.py       流程
    composer.py             已有
    qualification.py        B5 限定条件
    final_validation.py     校验组合
    numeric_validation.py   升级
    completion_rules.py     终态表
```

---

## 8. 一次校验的具体过程

```text
Data 证据   华东 2025-08 销售额 1285000.00
Knowledge   片段 17 含“工单和退货…原因假设”“该复盘不是…结论”

compose_report
  事实 fact-1：values=[{revenue/v1, 1285000.00, CNY, 华东, 2025-08, ev-1, 0, 销售额}]

证据复核（模型）
  verdict=supported, supported_chunks=[17], qualification_refs=[17.1, 17.2]

代码
  取回 17.1、17.2 原文 → 限定条件 2 条
  摘要：“华东 8 月销售额 128.5 万元。[17]”
    128.5 万 → 规范化 1285000 → 命中 fact-1 → 实体一致
  引用 17 属于本次检索和当前公司
  → schema✓ numbers✓ citations✓

决策   含因果假设？否 → completed → 发布
```

---

## 9. 失败路径

| 场景 | 系统行为 |
|---|---|
| 复核输出不合规 | 修复一次；再失败按决策表（只用代码事实生成 `partial`） |
| 编号指向不存在的句子 | 忽略并计数；全部无效时告警 |
| 数字校验失败 | 重规划（现有）；用完后安全文本 |
| 实体抽取不确定 | **只有明确冲突才判失败**；抽不到实体不算冲突 |
| 复核结论和代码校验矛盾 | 代码优先，写事件 |
| 人工审核超时 | 任务保持 `awaiting_review`，报告不发布；可配置提醒 |
| 恢复时重新校验 | 用相同证据和规则版本，结果相同 |

---

## 10. 配置

| 配置项 | 默认值 |
|---|---|
| `REVIEW_QUALIFICATION_MODE` | `text`（`text` / `sentence_ref`） |
| `NUMERIC_BINDING_MODE` | `off`（`off` / `shadow` / `enforce`） |
| `FACT_MAX_ROWS` | 5（现值） |

规则版本写入任务快照。

---

## 11. 落地步骤

**验证命令是计划，尚未运行。** 放宽或收紧校验都要批准。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B5 限定条件**（**需批准，付费**） | 句子切分和编号；复核提示词和结构；`qualification.py` | 第 2.2 节；冒烟连续 ≥ 5 轮不再缺限定 | `text` 模式 |
| **B9a 复核留存** | 事件 | 能回答“为什么重规划” | 无影响 |
| **B9b 事实结构化** | `facts.py`、`schemas.py`（报告 1.3） | 旧报告可读；新字段值正确 | 字段可空 |
| **B9c 数字绑定影子** | `numeric_validation.py` | 统计会被新规则拦下的情况，人工抽查 | `off` |
| **B9d 数字绑定启用**（**需批准**） | `enforce` | “华北 128.5 万”用例被拦；误判率可接受 | `shadow` |
| **B9e 派生指标和单位** | 代码计算、规范化 | 环比表驱动；万、亿、% 用例 | 开关 |
| **B10 终态表** | `completion_rules.py`；清理分散判断 | 表驱动；差异逐条批准 | revert |
| **拆文件** | 第 7 节 | 全量测试 | revert |

---

## 12. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 证据题重复 25 次 | 限定条件 25/25 保留（目标） |
| 把华东的数字写成华北的 | 校验失败 |
| 模型自造环比数字 | 校验失败 |
| 文档提供的数字写在摘要 | 只有引用了该片段才通过 |
| 预算耗尽 | 终态和限制码符合规则表 |
| 任一 `partial` 任务 | 有明确限制码和说明 |
| 重规划的任务 | 能查到复核结果和原因 |

**25/25 是目标。** 如果限定条件本身需要模型判断得对，选错句子的问题还会存在，只是不再因改写而丢失。这要在结果中分开统计。

**仍需开工时确认：** `reviewer_node` 的具体流程（这轮只读了前半部分）；`citation_validation.py` 的范围校验；`composer.py` 对多证据的合并方式；现有报告里 `partial` 的实际分布。
