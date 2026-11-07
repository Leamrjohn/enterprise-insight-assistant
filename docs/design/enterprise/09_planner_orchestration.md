# Planner 和主链实现设计

**状态：** 设计稿，未实现。文中代码是草案。对应总计划工单 B1、B2。

**不变的约束：** 主链顺序不变；所有重试和路由由代码决定；模型输出不能决定权限。任何改动主链结构的地方都要批准。

---

## 1. 现在怎么运行

```text
graph.py:107   8 个节点；MAX_GRAPH_STEPS=20
planner_node   nodes.py:158  PlannerAgent → planning.py:381 模型
                planner_decision.py:77 Pydantic 校验
                planner_decision.py:42 文档证据问题的路线规则
复核节点        nodes.py:245  第二次模型调用，可改写计划（review_plan）
                再跑一次路线规则（nodes.py:268）
分支           graph.py:42  按 action 和 route 进 Data / Knowledge / 终态
Reviewer 之后  router.py:70 choose_next_action：stop / retry / replan
```

**要保留的好设计：**
- 路由不问模型（`router.py:71`）。
- 检查点只允许恢复到白名单节点（`graph.py:21`）。
- `NodeOutcome` 是持久化的节点结果。
- 反问文字里的内部字段名由代码拦截（`nodes.py:70`）。
- 下游只看 `resolved_question`，不读历史。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| “缺不缺时间”全靠模型判断 | `planning.py:128` 只是提示词 | 判断随模型波动，判错就直接查库或错误反问 |
| 每个任务至少 2 次规划调用 | `graph.py:122` 固定经过复核 | 简单问题也多花一次；曾 15/30 次错误想反问【记录】 |
| 路线规则靠正则 | `planner_decision.py:24` | 只覆盖固定说法；“销售下降改写题”3 轮错 2 轮【记录】 |
| `period` 是自由文本 | `planner_decision.py:39` | 记忆、评估都要再解析，容易不一致 |
| 技术故障被说成用户问题 | `nodes.py:273-285` | 不可重试的复核失败时，告诉用户“请补充指标、时间” |
| 路由有新旧两套判断 | `router.py:80-110` 用 Outcome，`:112-168` 用旧状态 | 分支多，难以穷尽测试 |
| 复核结果不保存 | 【记录】任务 488 “为什么重规划未证实” | 只能重新付费复现 |
| 文件过大 | `nodes.py` 982 行 | 难改、难审 |
| 状态是大字典 | `state.py` 约 39 个键 | 范围字段和中间产物混在一起 |

---

## 2. 目标规划流水线

**主链节点不变，规划节点内部拆成 5 步：**

```text
第 1 步  提取事实  QuestionFacts（代码）
第 2 步  模型规划  Planner（模型提议）
第 3 步  结构校验  Pydantic（代码，已有）
第 4 步  规则裁决  PlanRules（代码）
第 5 步  按需复核  review_plan（模型，受策略控制）
```

### 2.1 第 1 步：提取事实（不调用模型）

```python
@dataclass(frozen=True)
class QuestionFacts:
    periods: tuple[Period, ...]         # 解析出的时间
    period_is_relative: bool            # “本月”“上季度”
    metrics: tuple[str, ...]            # 语义层命中的指标引用
    entities: tuple[EntityMatch, ...]   # 区域、客户、编号（SUP-003）
    wants_document: bool                # “根据资料”“哪些资料支持”
    wants_number: bool                  # “是多少”“统计”
    is_comparison: bool                 # “比较”“环比”
    is_causal: bool                     # “为什么”“原因”
    other_company_mentions: tuple[str, ...]
```

**数据来源：** 时间用规则解析器（复用 `rag/validity.py` 的解析并扩展）；指标和实体来自语义层（见 `10_data_sql.md`）；其余是确定词表。

**作用：** 放进 Planner 上下文作为“代码观察到的事实”，并供第 4 步使用。

### 2.2 第 4 步：规则裁决

规则按固定顺序执行，**每条都有编号和版本，命中就写事件 `plan_rule_applied`**。

| 编号 | 条件 | 动作 |
|---|---|---|
| R1 | 问题提到其他公司或平台内部 | 改为 `refuse` |
| R2 | 明确只要文档，没要数字 | `route=knowledge_only`（现有规则） |
| R3 | 既要文档又要数字 | `route=hybrid`（现有规则） |
| R4 | `route` 含数据 + 指标查询 + 无时间且会话状态也没有 | 改为 `needs_clarification`，缺 `time_range` |
| R5 | 比较问题缺比较期 | 改为反问，缺 `comparison_period` |
| R6 | 问题的指标不在语义层且无相关表 | 改为反问或说明不支持（含广告点击率这类） |
| R7 | `resolved_question` 丢失了问题里的实体或时间 | 退回 Planner 修复一次，再失败就反问 |
| R8 | 存在长期约束，但改写问题没有体现 | 同 R7 |

**规则只收紧，不扩大：** 可以把 `analyze` 改成反问或拒绝，不能把拒绝改成 `analyze`。

**误判风险：** 规则判错会把能答的问题变成反问。所以先走影子模式（只记录，不生效），对比评测后再逐条启用。

### 2.3 第 5 步：按需复核

**先测量，再决定。** 影子阶段继续每次复核，统计复核改变计划的比例和正确性：

| 结果 | 决定 |
|---|---|
| 复核经常纠正错误 | 保持每次复核 |
| 只在某类问题有用 | 只对 `hybrid`、因果问题、规则有冲突时复核 |
| 几乎不改变结果 | 关闭或只在高风险时触发 |

配置 `PLANNER_REVIEW_POLICY=always/conditional`。**这改变主链行为，需要批准。**

### 2.4 计划结构升级

```json
{
  "schema": "plan/2",
  "action": "analyze",
  "route": "data_only",
  "resolved_question": "华东区 2025 年 8 月已交付订单销售额是多少？",
  "intent": {"kind": "business_metric", "required_capabilities": ["销售额"]},
  "scope": {
    "entities": [{"type": "region", "value": "华东区"}],
    "periods": [{"start": "2025-08-01", "end": "2025-08-31", "raw": "2025 年 8 月"}]
  },
  "metric_refs": ["revenue/v1"],
  "applied_rules": []
}
```

`evaluation_scope` 保留一个版本用于兼容。**时间必须是代码解析或校验过的日期，** 模型写的时间与代码解析结果冲突时，以代码为准并写事件。

---

## 3. 技术故障和用户问题分开

现在复核失败时，用户可能被要求“补充指标、时间”，其实是系统故障（`nodes.py:273`、`:322`）。

| 情况 | 新终态 | 用户看到 | 是否可重试 |
|---|---|---|---|
| 确实缺信息 | `needs_clarification` | 具体问题 | |
| 模型临时不可用 | `failed`（`service_unavailable`） | “服务暂时不可用，请稍后重试” | 是 |
| 输出反复不合规 | `failed`（`planning_failed`） | “这个问题暂时处理不了，已记录” | 是 |
| 意图字段缺失 | 退回修复，再失败同上 | 同上 | 是 |

反问率因此可能下降，这是预期结果。评测要把“错误反问”单独计数。

---

## 4. 路由改成决策表（B2）

**把 `router.py` 的条件分支改成表，** 便于穷尽测试：

```python
ROUTING_TABLE: tuple[Rule, ...] = (
    Rule("citation_invalid", when=validation_failed("citations"), then="stop"),
    Rule("number_or_schema_invalid", when=validation_failed("numbers", "schema"),
         then="replan"),
    Rule("cancelled", when=any_outcome("cancelled"), then="stop"),
    Rule("denied", when=any_outcome("denied"), then="stop"),
    Rule("no_records", when=any_outcome("no_matching_records"), then="stop"),
    ...
)
```

| 要求 | 做法 |
|---|---|
| 行为不变 | 先生成全部状态组合，比对旧 `choose_next_action` 和新表的结果（差异为 0） |
| 重试有界 | 每个目标单独计数（`retry_data`、`retry_knowledge`、`replan` 都有上限），超限统一 `stop` |
| 删除旧分支 | `router.py:112-168` 只在兼容旧检查点时需要；确认无进行中的旧任务后再删 |
| 可解释 | 每次决策写规则编号和原因 |

---

## 5. 节点结构（B1）

**只移动，不改行为。** 每次一个节点、一个提交。

```text
workflow/orchestration/
    graph.py
    router.py
    state.py          TaskScope（冻结）+ Artifacts（产物）
    node_runner.py    统一包装
    nodes/
        planner.py  planner_review.py  terminal.py
        data.py  knowledge.py  reviewer.py  routing.py
```

**统一包装 `run_node`：** 现在每个节点都要自己写 `_set_stage`、异常转换和 `_checkpoint`。统一成：

```text
run_node(name, fn, state)
  1 检查取消
  2 设置阶段
  3 开 span（见观测设计）
  4 执行 fn
  5 校验 NodeOutcome
  6 写检查点
```

**状态拆分：**

| 类型 | 字段举例 | 规则 |
|---|---|---|
| `TaskScope` | `user_id`、`company_id`、`document_ids`、数据源、快照 | 创建后不可变；不从检查点覆盖（`graph.py:65` 已有此原则） |
| `Artifacts` | `plan`、`data_result`、`knowledge_result` | 节点产出，可进检查点 |
| 运行时对象 | `tool_runtime`、回调 | 不进检查点 |

---

## 6. 一次规划的具体过程

| 问题 | 第 1 步事实 | 模型提议 | 规则裁决 | 结果 |
|---|---|---|---|---|
| 华东区销售额是多少？ | 指标 `revenue/v1`；实体华东；无时间 | 可能 `analyze` 或反问 | **R4** | 反问：“要查询哪个时间范围？” |
| 那华北呢？（有状态） | 实体华北；状态有时间和指标 | `analyze`，改写完整 | 通过 | `data_only` |
| 哪些资料支持 SUP-003 批次异常？ | `wants_document`；编号 SUP-003 | 可能 `hybrid` | **R2** | `knowledge_only` |
| 本月广告点击率是多少？ | 时间相对；指标未命中 | 不定 | **R6** | 说明当前没有这个指标 |
| 请给出 8 月销售额，并根据资料说明原因 | 指标 + 文档 + 因果 | `hybrid` | R3 | `hybrid` |
| 查一下 Beta 公司的销售额 | 其他公司 | 不定 | **R1** | 拒绝 |

**这里的 R1 不是安全边界。** 真正的隔离在 SQL 和数据源层，它只是让回答更清楚。

---

## 7. 失败路径

| 场景 | 系统行为 |
|---|---|
| 第 1 步提取出错 | 写事件，事实为空，继续走模型；规则只用已知事实 |
| 模型超时 | 网关处理；最终失败走第 3 节 |
| 规则之间冲突 | 按编号顺序，第一条终止性规则生效；写事件 |
| R7 修复后仍失败 | 反问，不发错误问题到下游 |
| 重规划次数用完 | 按决策表 `stop`，输出已有证据和限制 |
| 崩溃恢复 | 从白名单节点恢复；规则版本来自任务快照 |

---

## 8. 配置

| 配置项 | 默认值 |
|---|---|
| `PLAN_RULES_MODE` | `shadow`（`off` / `shadow` / `enforce`） |
| `PLAN_RULES_VERSION` | `1`，写入快照 |
| `PLANNER_REVIEW_POLICY` | `always` |
| `ROUTER_TABLE_ENABLED` | `false`，迁完删除 |
| `MAX_REPLANS` / `MAX_RETRY_DATA` / `MAX_RETRY_KNOWLEDGE` | 现有上限（`router.py:16`）拆开 |

---

## 9. 落地步骤

**验证命令是计划，尚未运行。** 评测脚本的参数开工时确认。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B1a 拆节点** | `orchestration/nodes/`，行为不变 | 全量测试和冒烟不变 | revert |
| **B1b `run_node`** | 统一包装 | 取消、检查点、阶段测试通过 | revert |
| **B2a 复核结果落库** | 复核决定写事件（只有决定和字段差异，不写原文） | 能回答“为什么重规划” | 不影响业务 |
| **B2b 技术故障分离**（改用户可见行为） | `nodes.py:273`、`:322` | 注入故障后不再要求用户补信息 | revert |
| **B2c QuestionFacts** | `planner/facts.py`，只放进事件 | 表驱动测试；大量真实问法 | 不影响业务 |
| **B2d 规则影子** | `planner/rules.py`，`shadow` | 跑路由评测，统计每条规则的命中和对错 | `off` |
| **B2e 规则启用**（**需批准**） | 逐条切 `enforce` | 路由评测高于 43/48；错误反问不增加 | 单条关闭 |
| **B2f 结构化时间** | 计划 `plan/2` | 记忆和评估都用同一时间 | 保留旧字段 |
| **B2g 复核策略**（**需批准，改主链行为**） | 按 2.3 决定 | 准确率不降；规划调用减少 | `always` |
| **B2h 路由决策表** | `router.py` | 全组合比对差异 0 | 开关 |

**费用：** 路由评测有录音时可回放；改了规划提示词就要重新录制，要先批准。

---

## 10. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 缺时间问题连跑 15 次 | 15 次都反问，且问的是时间 |
| 文档问题连跑 15 次 | 全部 `knowledge_only` |
| 改写题连跑 15 次 | 比当前 3 轮错 2 轮明显改善 |
| 注入模型故障 | 用户看到的是服务提示，不是补信息 |
| 任一任务 | 能查到命中的规则和路由原因 |
| 路由表 | 和旧函数全组合比对差异 0 |
| 规划调用数 | 有基线和变化报告 |

**仍需开工时确认：** `review_plan` 的实际提示词（这轮只读到调用点）；`rag/validity.py` 的时间解析能覆盖多少说法；现有检查点是否还有依赖旧状态字段的任务。
