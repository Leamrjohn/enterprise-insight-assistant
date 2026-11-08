# 改造后一个任务怎么运行

**状态：** 目标形态，未实现。它把工具、上下文、记忆三份设计串起来，按真实运行顺序走一遍。数字和编号都是示例。

**场景：** 用户已问过“只看已交付订单。华东区 2025 年 8 月销售额？”，现在追问：**“那华北呢？”** 用户是 12 号公司的 analyst。

**主链结构不变：** API 写任务和 Outbox → Worker 认领 → Planner → Data / Knowledge → Reviewer → 确定性校验 → 持久化发布。

---

## 1. 全过程

```text
浏览器 ─POST 消息→ API
                   ├ 鉴权、限流、配额
                   ├ 冻结：消息历史 + 会话状态 + 配置哈希 + 工具目录哈希
                   └ 同一事务写 任务 + Outbox
Beat ─发布 Outbox→ Redis → Worker 认领（新 execution_id、开始续约）
Worker
  ├ 选择记忆（权限 → 召回 → 打分）
  ├ Planner：上下文引擎组装 → 预占预算 → 模型 → 结构化校验
  ├ Data：SQL 生成 → 语义复核 → 工具流水线 → 结果评估
  ├ Reviewer：组装报告 → 证据复核 → 确定性校验
  └ 发布：条件更新（令牌校验）→ 记忆 → 会话状态
浏览器 ─轮询→ API → 报告
```

---

## 2. 逐步说明

### 第 1 步：API 接收（Worker 之前）

| 做什么 | 依据或来源 | 结果 |
|---|---|---|
| 校验令牌和成员关系 | 现有 | 用户 88，公司 12 |
| 按用户和公司限流 | 总计划 A1 | 未超限 |
| 检查公司月度和用户日配额 | 总计划 G8 | 未超限 |
| 取历史消息，生成快照 | `conversations/service.py:216` | 最近消息 |
| **复制会话状态到快照** | 设计 02 第 3 节 | 见下 |
| **解析配置：默认 → 环境 → 公司策略** | 总计划 K3 | 生成 `config_snapshot_hash` |
| 同一事务写任务和 Outbox | 现有 | 任务 1002 |

冻结进任务的内容：

```json
{
  "context_snapshot": {
    "history": ["…最近消息…"],
    "state": {
      "subject": {"metric": "销售额", "entities": ["华东区"], "period": "2025-08"},
      "standing_constraints": [{"text": "只看已交付订单", "source_message_id": 812}]
    }
  },
  "tool_policy_snapshot": {"allowed_tools": ["rag_search", "sql_query", "template_query"],
                           "catalog_hash": "9c1e…"},
  "model_policy_snapshot": {"profiles": "default/3", "prompt_set": "2026-11-20"},
  "context_policy_set": "v1",
  "config_snapshot_hash": "41be…"
}
```

**为什么要冻结：** 配置在任务运行中被修改，也不影响这个任务；崩溃恢复后也完全一样。

### 第 2 步：投递和认领（现有机制不变）

Beat 每 5 秒发布 Outbox。Worker 用 `claim_execution` 认领，得到新的 `execution_id`，心跳线程开始续约。

### 第 3 步：选择记忆

```text
权限     用户启用、成员已批准、角色 analyst → 只能读 min_view_role='any'
查询文本 “那华北呢” + 快照 subject → 华北 / 销售额 / 2025-08 / 华东区
数据库   最多 200 条候选（有索引，不再全量读取）
过滤     来源文档仍可见
打分     选中 2 条，都是之前的华东记忆
写事件   context_selected（已有），记录选中和丢弃的原因
```

查询失败时，写事件后继续，记忆为空。记忆不是必需品。

### 第 4 步：Planner

**上下文引擎生成 `ContextPack`（策略 `planner/2`，预算 3000）：**

| 区段 | 信任 | 原始 token | 最终 token | 处理 |
|---|---|---|---|---|
| 规则和输出契约 | system | 1150 | 1150 | 固定 |
| 冻结范围 | control | 40 | 40 | |
| 会话状态 | user | 60 | 60 | 必需 |
| 历史 | untrusted | 900 | 620 | 压缩旧的助手回复 |
| 记忆 | untrusted | 210 | 210 | |
| 当前问题 | user | 10 | 10 | 必需 |

合计 2090，在预算内。**如果放不下：** 依次压缩历史、丢记忆；还放不下就不调用模型，直接反问。

**模型调用：**

```text
reserve_model_call   检查预算 → 写 reserved 记录（含 prompt 版本、context 清单）→ 提交
gateway.chat         profile: 模型 v4-flash，温度 0.2，超时 30 秒
record_model_call    用实际用量结算，比较估算偏差
```

**模型返回的计划（经 Pydantic 校验）：**

```json
{
  "action": "analyze",
  "route": "data_only",
  "resolved_question": "华北区 2025 年 8 月已交付订单销售额是多少？",
  "evaluation_scope": {"entities": ["华北区"], "period": "2025-08"},
  "standing_constraint_ids": [812]
}
```

**代码接着做确定性检查：** 文档证据问题的路线规则（`planner_decision.py:42`）；`standing_constraint_ids` 必须是该用户消息；然后写检查点。

### 第 5 步：Data

| 子步骤 | 现有还是新增 | 说明 |
|---|---|---|
| 组装 SQL 上下文 | **新增引擎**（策略 `sql/1`） | 问题、筛选后的表结构、已批准术语 |
| 生成 SQL | 现有 | 只拿 `resolved_question`，不看历史和记忆 |
| 查询契约检查 | 现有 | `data_agent.py:183` |
| 语义复核 | 现有，上下文新增 | 模型判断，不是安全边界 |
| 指标评估 | 现有 | `data_agent.py:273` |
| **工具流水线** | **新增** | 13 步，见设计 01 |
| 结果评估 | 现有 | `data_agent.py:311` |

工具流水线在这里实际做的事：

```text
登记 ✓ 策略快照 ✓ 取消检查 ✓ 用户和角色 ✓ 参数 ✓
范围：覆盖为任务的公司 12 和冻结的数据源
配额：3 → 4
熔断：sql_query:12 → closed
执行：validate_sql（单条 SELECT、表在快照内）
      → 公司 12 的只读连接 → statement_timeout 10 秒
结果：1 行，38 token，未超限
审计：logical_call_id=…, attempt_no=1, succeeded, catalog_hash=9c1e…
```

### 第 6 步：Reviewer 和确定性校验

```text
compose_report        代码组装报告草稿
证据复核               引擎组装（策略 evidence_review/2）→ 模型
                      记忆在不可信区段，只用来发现矛盾
                      _credible_memory_flags 由代码判断是否可信
_validate_final_answer 校验 schema、数字、引用
smart_router          代码决定：通过 / 重规划 / 停止，不问模型
validate_report       保存前再校验一次
decide_completion     决定 completed / partial / awaiting_review
```

### 第 7 步：发布

```text
transition_execution  条件：active_execution_id == 当前 execution_id 且状态 running
                      0 行更新 → 自己已失去所有权 → 什么都不再写
persist_report_memory 主题键(12|delivered_revenue|华北区|2025-08)，TTL 30 天
更新 conversation_states  subject 换成华北；约束保留；乐观锁 version+1
同步助手消息
提交
```

### 第 8 步：前端和排查

前端轮询拿到报告，显示数字和引用。任何人事后都能按任务号还原：

```text
任务 1002  completed  公司 12  用时 11.2 秒  $0.0027  配置 41be  工具目录 9c1e
├ memory    选中 2，丢弃 0
├ planner   prompt=planner@3.1  context=planner/2  2090→实际 2118 token  结果 data_only
├ data      prompt=sql@2.0  context=sql/1
│  ├ sql_review  通过
│  └ sql_query   1 次逻辑调用 / 1 次执行  48ms  1 行
├ reviewer  prompt=evidence@1.4  supported
├ validate  schema✓ numbers✓ citations✓
└ memory+state  已写入
```

这是 `render_task_trace.py` 的目标输出。

---

## 3. 出错时怎么走

| 哪里出错 | 谁发现 | 接下来怎样 | 用户看到 |
|---|---|---|---|
| 配额用完 | API | 不建任务 | 明确提示配额，429 |
| Planner 上下文放不下 | 引擎 | 不调用模型，直接反问 | “请缩小范围” |
| 模型超时 | 网关 | 重试 → 备用模型 → 明确失败 | 成功，或可重试的失败 |
| 模型返回格式错误 | Pydantic | 修复调用（受修复上限约束） | 无感知或失败 |
| 模型输出被截断 | 网关 | 明确错误码，不当内容错误 | 任务按错误结束 |
| 模型预算耗尽 | 预占 | 抛 `ModelBudgetExceeded` | 已有数据可给 `partial` |
| 经营库故障 | 流水线 | 重试 1 次 → 计入熔断 | 明确失败；同公司后续任务快速失败 |
| SQL 校验不过 | `validate_sql` | CALLER → 修复一次 | 无感知或失败 |
| 权限被收回 | 流水线第 4 步 | DENIED，停止 | 无权限 |
| 用户取消 | 流水线第 3 步或预占 | TASK_STOP，已有审计保留，不再写结果 | 已取消 |
| Worker 崩溃 | 心跳停止 → 租约到期 | Beat 回收，新 Worker 从检查点继续；未结算调用标 `unknown` | 变慢，结果不变 |
| 旧 Worker 复活 | 条件更新 0 行 | 不写入任何内容 | 无感知 |
| 记忆查询失败 | Worker | 记事件，继续 | 无感知 |
| 数字校验失败 | 确定性校验 | 重规划或安全失败文本 | 不发布错误数字 |
| 引用校验失败 | 确定性校验 | 停止（安全类） | 不发布 |

**这里有一项还没解决：** 恢复时 `.delay` 失败可能让任务卡在 `retrying`（总计划 B11）。其他行为都有现有代码或设计依据，但新增部分都要实现后才算成立。

---

## 4. 上线切换怎么进行

三个平台都有开关，可以一个节点一个节点切换，不用一次改完。

| 阶段 | `TOOL_PIPELINE_MODE` | `CONTEXT_ENGINE_MODE` | 记忆 | 切换依据 |
|---|---|---|---|---|
| 现在 | `legacy` | `off` | 只有 fact | |
| 切工具 | `enforce` | `off` | 同上 | 工具测试、冒烟不变差 |
| 上下文影子 | `enforce` | `shadow` | 同上 | 看到每节点差异，无费用增加 |
| 上下文切换 | `enforce` | `enforce`（逐节点） | 同上 | 路由、SQL、Knowledge 不降 |
| 记忆升级 | `enforce` | `enforce` | 结构化 fact + 会话状态 | 记忆和长对话评测不降 |
| 语义记忆 | `enforce` | `enforce` | 增加术语（按公司） | 评测有提升 |

**每次切换的固定动作：**

```text
1 备份（涉及迁移时）
2 部署，开关保持旧值
3 跑冒烟，确认部署本身没有影响
4 打开开关
5 跑冒烟和对应评测，与切换前逐题对比
6 变差 → 关开关并记录；不变差 → 观察一段时间后删除旧路径
```

冒烟命令（在项目根目录，它通过 `agent-worker-1` 执行）：

```bash
python backend/scripts/evaluation/run_smoke_tests.py --run-id <本次编号>
```

**凡是批量调用模型的运行，都要先报预计次数和费用级别，等批准。**
