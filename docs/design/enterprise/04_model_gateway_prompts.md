# 模型网关和提示词实现设计

**状态：** 设计稿，未实现。文中代码和 SQL 是草案。对应总计划工单 G1～G9。

**不变的约束：** 调用前检查预算（ADR-0001 后为软上限，见下）；失败不当免费；模型输出未通过校验不能当结果；不能发布未经确定性校验的内容。

**ADR-0001 修订（2026-11-07）：** 已选方案 D。LiteLLM SDK 加 Router 负责重试、`Retry-After`、备用和冷却；预算改为调用后记账加软上限（I1′）；配置冻结（I2）保留；不用 Proxy。下文标“ADR-0001”的段落是方案 D 的做法。**原文保留**，作为 V1 或 V2 验证不通过时的退路（方案 B：只用 SDK，重试和备用自建）。详见 [ADR-0001](../adr/0001-gateway-observability-build-or-buy.md)。

---

## 1. 现在怎么运行

```text
业务代码     planning.py:381 self._gateway.chat(prompt, system_prompt, json_mode=True)
网关工厂     factory.py:10   lru_cache 单例：全进程一个 DeepSeekGateway
一次调用     deepseek.py:113 从任务快照取输出上限和超时（温度取全局配置 :71）
预占         deepseek.py:123 reserve_model_call → 检查预算、写 reserved、提交
请求         deepseek.py:159 OpenAI SDK（max_retries=0，deepseek.py:67）
结算         deepseek.py:220 record_model_call → 按实际用量更新
临时错误     deepseek.py:234 记录 → next_fallback_model → 否则抛 RetryableModelError
上层重试     planning.py:386、semantic_review_service.py:417、tool_loop.py:134 各自重试
```

**要保留的好设计：** 预占和结算；未知费用单独计（`model_governance.py:476`）；价格和预算随任务冻结；录制回放找不到记录时直接失败（`replay.py:60`），不会误付费。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| 全局一个温度和输出上限 | `settings.py:98-99` | 裁判节点也带随机性；回款题曾 25 次误删 5 次【记录】 |
| 温度没有冻结 | `deepseek.py:71` | 改配置影响进行中的任务 |
| 改写单例状态 | `deepseek.py:254` | 一旦多线程，模型可能串 |
| 备用模型恒空 | `workflow/repository.py:99` | 切换逻辑实际从未运行 |
| 重试散在各调用方 | 见上 | 规则不一致；每次重试都占 `calls` |
| 不读 `Retry-After`，无熔断 | `deepseek.py:234` | 供应商故障时反复撞墙 |
| 截断只告警 | `deepseek.py:212` | 半截 JSON 被当成“内容错误”，后面去修复 |
| 只有任务级预算 | `workflow/lifecycle/model_budget.py:10` | 一家公司可以花光全部额度 |
| `prompt_version` 从不传 | `tasks.py:665` | 指标变化说不清是哪版提示词 |
| 提示词是代码里的字符串 | `planning.py:68`、`sql_generation.py:88` 等 | 无版本、无评审线索 |
| 按全价计费 | `model_governance.py:224` | 没算缓存命中价，账本可能偏高 |
| 无出站控制 | `gateway/base.py:7` 只是注释 | 经营数据直接发给外部模型 |
| `core` 依赖 `modules` | `deepseek.py:31` | 依赖方向反了 |
| DeepSeek 和 OpenAI 两份网关 | `gateway/openai.py` | 同样的逻辑写两遍 |

---

## 2. 目标结构

```text
backend/app/modules/runtime/models/
    request.py     ModelRequest、ModelResponse（不可变）
    errors.py      ModelErrorKind 和处理规则
    profiles.py    ModelProfile、ProfileSet
    router.py      ModelRouter：重试、备用、熔断、账本（唯一入口）
    structured.py  call_structured：解析 + 修复
    outbound.py    出站检查
    transcript.py  脱敏留痕
    providers/
        base.py               ProviderClient（无状态）
        openai_compatible.py  DeepSeek、OpenAI 共用
        local.py、replay.py
backend/app/prompts/
    manifest.json
    planner/system.md、sql/generate_system.md …
backend/app/modules/runtime/prompts.py   PromptRegistry
```

`core/gateway/` 保留一层薄外壳，让现有 `gateway.chat(...)` 调用不用一次全改；全部迁完后删除。

### 2.1 按用途配置模型

现在的节点名太粗：`data` 里同时有 SQL 生成和 SQL 复核。新增“用途”：

| 用途 | 现在位置 | 温度初值 | 输出上限 | 超时 |
|---|---|---|---|---|
| `planner` | `planning.py:381` | 0 | 1024 | 30s |
| `planner_review` | `nodes.py:262` | 0 | 512 | 30s |
| `sql_generate` | `sql_generation.py:324`、`:346` | 0 | 1024 | 30s |
| `sql_review` | `data_agent.py:221` | 0 | 512 | 30s |
| `knowledge_answer` | `knowledge/agent.py:146` | 0.2 | 1024 | 30s |
| `support_check` | `rag/support.py:186` | 0 | 512 | 30s |
| `evidence_review` | `semantic_review_service.py:412` | 0 | 1024 | 30s |
| `tool_loop` | `tool_loop.py:133` | 0.2 | 1024 | 30s |

现在全部是 0.2 和 1024。**改温度要付费验证（G3），不是直接改完就算。**

```python
@dataclass(frozen=True)
class ModelProfile:
    purpose: str
    provider: str
    model: str
    temperature: float
    max_output_tokens: int
    timeout_s: int
    json_mode: bool
    fallback: tuple[str, ...]   # 其他 profile 名称，可为空
```

**整组配置档有版本（如 `default/3`）。** 建任务时连同内容复制进 `model_policy_snapshot`，运行中和恢复后都不变。这样也修复了“温度没有冻结”的问题。

### 2.2 调用流程（`ModelRouter.complete`）

```text
输入：ModelRequest（purpose、prompt 引用、system、user、ContextManifest）

1 取配置档：从任务快照按 purpose 查
2 取消检查（已在预占里，保留）
3 出站检查：不通过 → ModelOutboundDenied，不发送、不计费
4 logical_call_id = uuid4()
5 for profile in [主配置, *备用]:
     for attempt in 重试次数:
       a 熔断打开？→ 换下一个配置
       b reserve_model_call（第一次占 calls；重试不占）
       c provider.complete(不可变请求, 超时)
       d 成功 → 校验 finish_reason
                结算 → 留痕 → 返回
       e 失败 → 分类 → 记录 → 决定 重试 / 换配置 / 抛出
6 全部失败 → 抛 ModelUnavailable
```

**`ProviderClient` 不保存模型名和温度：** 所有参数都从请求传入，天然不会串模型。

**ADR-0001：方案 D 的调用流程**

```text
1 取配置档版本（任务快照，如 default/3）→ 取或构造该版本的 LiteLLM Router（按版本缓存，同版本复用）
2 取消检查
3 出站检查：不通过 → ModelOutboundDenied，不发送、不计费
4 logical_call_id = uuid4()
5 软上限检查：已结算 + 在途估算 + 本次估算 ≤ 上限，否则 ModelBudgetExceeded
6 router.completion(...)：重试、Retry-After、备用、冷却由 Router 执行
     每次物理尝试 → 回调 → 写一条尝试记录（实际模型、结果、用量；失败记 unknown）
7 成功 → 校验 finish_reason → 结算 → 留痕 → 返回
8 失败 → 把 LiteLLM 异常映射成 ModelErrorKind → 抛出
```

第 6 步能否记全每次尝试，取决于 ADR 验证项 V1；Router 是否会和底层 SDK 重试相乘，取决于 V2。

### 2.3 错误分类和处理

| 分类 | 来自 | 重试 | 换备用 | 计入熔断 | 费用 |
|---|---|---|---|---|---|
| `timeout` | `APITimeoutError` | 1 次 | 是 | 是 | 未知，保留预占 |
| `connection` | `APIConnectionError` | 1 次 | 是 | 是 | 未知，保留预占 |
| `rate_limited` | `RateLimitError` | 按 `Retry-After`，超过剩余时间就不等 | 是 | 否 | 未知 |
| `server_error` | `InternalServerError` | 1 次 | 是 | 是 | 未知 |
| `empty_or_malformed` | `deepseek.py:176`、`:180` | 1 次 | 否 | 否 | 有用量时按实际 |
| `truncated` | `finish_reason=length` | 否 | 否 | 否 | 实际，抛明确错误 |
| `request_invalid` | 4xx（配置问题） | 否 | 否 | 否 | 无，**告警** |
| `budget` | 预占失败 | 否 | 否 | 否 | 无，任务级停止 |
| `cancelled` | 预占发现取消 | 否 | 否 | 否 | 无，任务级停止 |

**移除上层重试：** `planning.py:386`、`semantic_review_service.py:417`、`tool_loop.py:134` 的网络重试要去掉，否则 2 层重试会乘起来。上层只保留**业务修复**（比如 JSON 不合契约）。

**ADR-0001：** 上表的“重试”“换备用”两列改为 Router 的 `retry_policy` 和 `fallbacks` 配置，按错误类型设置；`truncated`、`request_invalid`、`budget`、`cancelled` 配成不重试、不换备用。“计入熔断”一列对应 Router 的冷却。`rate_limited` 在 Router 里会按 `Retry-After` 冷却，和上表“不计入熔断”不同，要在 V 验证里确认实际行为再定。自建部分只剩**异常映射**：把 LiteLLM 的异常类型映射到上表的分类。

**时间上限：** 一次逻辑调用总耗时不超过 60 秒（现有规则：单次超时不超过租约的一半，`settings.py:13`）。心跳在独立线程，退避时不会丢租约。

### 2.4 预算规则改动

| 规则 | 现在 | 改造后 |
|---|---|---|
| `calls` | 每次物理调用都加 1 | 只有**逻辑调用**加 1 |
| `retries` | 无 | 新增计数，上限 `max_network_retries` |
| 费用 | 未知时保留预占 | **不变**：可能已被收费，不能当免费 |
| `tokens` | 失败时保留预占 token | 拆成 `tokens`（已结算）和 `unknown_tokens` |

这样网络抖动不会把正常任务判成“调用超限”，费用上限仍然保护到位。**这改变了预算语义，需要批准。**

**ADR-0001：费用从“调用前预占”改为“调用后记账加软上限”（I1′）。** 调用前只检查“已结算 + 在途估算 + 本次估算”；调用后按实际用量结算。失败仍记未知费用，不当免费。最多超出“并发数 × 单个逻辑调用的最大物理尝试数 × 单次费用上限”，具体值由 V6 测出（一次 Router 请求可能含多次重试和备用切换）；记账前崩溃的补记由 V7 验证。**提高并发（B13）之前要重新计算这个值，写回 ADR。** `calls` 和 `retries` 的拆分不变，`retries` 由回调计数。

### 2.5 一次调用的具体过程

SQL 生成，主模型第一次超时，重试成功：

| logical_call_id | 配置 | attempt | 结果 | 账单 | 用时 |
|---|---|---|---|---|---|
| a1… | sql_generate | 1 | timeout | unknown，保留 $0.0009 | 30.0s |
| a1… | sql_generate | 2 | success | settled $0.0007 | 4.1s |

任务 `model_budget_usage`：`calls=3`（只加 1）、`retries=1`、`unknown_cost_calls=1`。

### 2.6 结构化输出统一处理

`Planner`、`SQL`、语义复核现在各写一套解析和修复。统一为：

```python
def call_structured(router, request, schema, *, max_repairs=1) -> BaseModel:
    response = router.complete(request)
    for attempt in range(max_repairs + 1):
        try:
            return schema.model_validate_json(response.text)
        except ValidationError as error:
            if attempt == max_repairs:
                raise StructuredOutputError(...)
            response = router.complete(request.repair(error_summary(error)))
```

修复调用标记 `is_repair`，继续受现有 `max_repairs` 约束。发给模型的错误摘要只含字段路径，不含原始值。

---

## 3. 提示词注册表

### 3.1 文件和清单

```text
backend/app/prompts/planner/system.md
```

```json
{
  "planner.system": {
    "version": "3.1.0",
    "file": "planner/system.md",
    "variables": [],
    "sha256": "…",
    "eval_suite": "planner_route",
    "last_eval_run": "20261120-…"
  },
  "sql.generate_system": {
    "version": "2.0.0",
    "file": "sql/generate_system.md",
    "variables": ["schema_section", "metric_section"],
    "sha256": "…",
    "eval_suite": "sql_result",
    "last_eval_run": "…"
  }
}
```

**渲染用标准库 `string.Template`，不增加依赖。** 变量缺失或多余都报错。

### 3.2 运行规则

1. 启动时校验：文件存在、哈希一致、变量声明正确。不一致就启动失败。
2. 建任务时把 `prompt_set` 写进快照；账本 `prompt_version` 记录 `planner.system@3.1.0`。
3. 现有的 `prompt_template_id`（系统提示词哈希）继续保留，用来发现“版本相同但内容不同”。

### 3.3 变更门禁（CI）

```text
内容改了但版本没升            → 失败
版本升了但 last_eval_run 没更新 → 失败
eval_suite 的指标低于基线      → 失败
```

**录制回放的影响：** 回放按请求全文计算键（`replay.py:28`）。提示词一改，旧录音全部失效，并直接失败。这是好事（不会误判），但意味着**每次改提示词都要重新录制，有费用，要先批准**。可以把多个提示词改动合并后再录，以降低费用。

---

## 4. 出站数据控制

**公司策略 `egress_policy`（默认 `masked`）：**

| 策略 | 行为 |
|---|---|
| `allow` | 除禁止类外都可发送（要显式设置） |
| `masked` | 敏感字段脱敏后发送 |
| `internal_only` | 只能用内部模型；没有内部模型就拒绝调用，任务明确失败 |

**检查顺序（在预占之前）：**

```text
1 ContextPack 每段带数据分级标签（来自工具定义、字段分级表）
2 策略不允许的段 → 脱敏或拒绝
3 对全文做一次模式扫描（手机号、证件号、密钥）作兜底
4 结果写进 manifest：每段的分级和处理；不写原文
```

**字段分级来源：** 总计划 A10 的分级表；复用 `sql_executor.py` 的 `_mask_sensitive_rows` 和 `core/redaction.py`，不再各写一套。

**脱敏的代价：** 脱敏后模型可能答不了相关问题。评测要加“脱敏前后的准确率”。这是业务决定，所以默认值需要批准。

---

## 5. 脱敏留痕

```sql
CREATE TABLE model_call_transcripts (
  model_call_id varchar(36) PRIMARY KEY
      REFERENCES model_call_records(model_call_id) ON DELETE CASCADE,
  company_id integer NOT NULL,
  task_id integer NOT NULL,
  request_redacted jsonb NOT NULL,
  response_redacted jsonb,
  redaction_version varchar(32) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
ALTER TABLE model_call_transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_call_transcripts FORCE ROW LEVEL SECURITY;
CREATE INDEX ix_transcripts_expires ON model_call_transcripts (expires_at);
```

- **写入：** 结算之后单独提交。留痕失败只告警，不影响任务。
- **读取：** 只有管理员可读，每次读取写审计。
- **清理：** Beat 每天删除过期记录，默认 7 天。
- **为什么先放数据库：** 量小（现在约每周 1100 次调用【记录】），且能用 RLS。上线级再考虑对象存储和加密。

这解决了“任务 371 丢句”这类低频问题只能付费复现的情况。

---

## 6. 公司和用户配额

```sql
CREATE TABLE usage_quota_counters (
  company_id integer NOT NULL,
  user_id integer NOT NULL DEFAULT 0,     -- 0 表示公司级
  period varchar(10) NOT NULL,            -- 2026-11 或 2026-11-20
  cost_reserved numeric(12,6) NOT NULL DEFAULT 0,
  cost_settled numeric(12,6) NOT NULL DEFAULT 0,
  calls integer NOT NULL DEFAULT 0,
  PRIMARY KEY (company_id, user_id, period)
);
-- 开启并强制 RLS
```

**两处检查：**

| 位置 | 目的 | 失败结果 |
|---|---|---|
| API 建任务（`workflow/repository.py:24` 的准入） | 明显超限就不建任务 | 429，提示配额 |
| `reserve_model_call` 内 | 防止并发时超额 | `ModelBudgetExceeded` |

**并发安全：** 用条件更新，`UPDATE … SET cost_reserved = cost_reserved + :x WHERE cost_settled + cost_reserved + :x <= :limit RETURNING`，更新 0 行就是超限。

**加锁顺序：** 先任务行，再配额行，全项目统一。项目曾因锁顺序相反发生死锁（`dcc5494`，【记录】），要有并发测试。

**ADR-0001：** 配额仍然自建，不用 LiteLLM Proxy。随 I1′ 改为软上限：`reserve_model_call` 处的条件更新改成“按估算检查”，结算时再把实际费用累加到 `cost_settled`。`cost_reserved` 列改记在途估算，结算后扣回。超出量同上，最多“并发数 × 单个逻辑调用的最大物理尝试数 × 单次费用上限”。

---

## 7. 备用模型和账单

**备用模型：** 需要决定备用是谁。同供应商的另一模型挡不住供应商整体故障；不同供应商意味着数据发给第二家，要过出站策略。**建议先做机制和模拟测试，备用配置留空，等决定。**

切换后账本记录实际模型，报告元数据标注 `fallback_used`。

**ADR-0001：** 备用清单仍写进任务快照（I2 保留），构造 Router 时转成它的 `fallbacks` 配置；冷却状态放 Redis，多个 Worker 共享（验证项 V3）。

**缓存计价：** 价格表增加 `prompt_cache_hit_per_1k`，`_priced_cost` 使用已记录的命中和未命中 token（`deepseek.py:48`）。

**账单核对：** 定时任务按天汇总账本；再把供应商账单（API 或人工导入 CSV）放进对账表；差异超过 5% 告警。未知费用调用单独列出。

---

## 8. 配置

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `MODEL_ROUTER_MODE` | `legacy` | `legacy` / `litellm`（方案 D）/ `enforce`（自建，退路），迁完后删除 |
| `MODEL_BUDGET_MODE` | `hard` | `hard`（调用前预占）/ `soft`（I1′）；G4 批准后改为 `soft` |
| `MODEL_PROFILE_SET` | `default/1` | 写入快照 |
| `MODEL_MAX_NETWORK_RETRIES` | 1 | 每个配置档 |
| `MODEL_LOGICAL_DEADLINE_S` | 60 | 不超过租约一半 |
| `MODEL_BREAKER_THRESHOLD` | 5 | 窗口内失败次数 |
| `MODEL_BREAKER_COOLDOWN_S` | 30 | |
| `MODEL_TRANSCRIPT_ENABLED` | `false` | 批准后开启 |
| `MODEL_TRANSCRIPT_RETENTION_DAYS` | 7 | |
| `MODEL_EGRESS_DEFAULT` | `masked` | 公司策略可改 |
| `QUOTA_ENFORCEMENT` | `off` | `off` / `observe` / `enforce` |
| `PROMPT_SET` | `2026-11` | 写入快照 |

配置档内容放进版本库（`profiles.py`），不用环境变量逐项配置；环境变量只选用哪一组。密钥只从环境或密钥服务读取。

---

## 9. 落地步骤

每个工单一个提交。**验证命令是计划，尚未运行。**

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **G1 提示词注册表** | 新增 `app/prompts/`、`runtime/prompts.py`；**内容逐字迁移**；`tasks.py:665` 等传版本 | 迁移前后系统提示词哈希一致（测试断言）；新任务 `prompt_version` 空值率 0 | revert，无数据变化 |
| **G2 配置档和不可变请求** | 新增 `runtime/models/`；用途 scope；`provider` 无状态；`legacy` 不变 | 并发 2 线程不串模型；单元测试；哈希不变所以回放仍命中 | 模式切回 `legacy` |
| **G3 裁判温度 0**（**付费，需批准**） | 改配置档，升版本 | 回款题重复 25 次；冒烟连续 3 轮；费用不升 | 换回旧配置档 |
| **V 方案 D 验证**（**引入依赖需批准**） | 单独虚拟环境；用模拟返回和假供应商测 ADR 第 5.1 节 V1～V7；不改项目依赖、不调真实模型 | 5 项都有可重复测试和结论，写回 ADR | 不涉及项目代码 |
| **G4 路由器、错误分类、重试**（**改预算语义，需批准**） | `router.py`；删上层网络重试；`calls` 语义调整；迁移加字段 `logical_call_id`、`attempt_no`、`error_kind` | 用假供应商注入每类错误，逐一断言重试次数、账本和预算；注入抖动后不判超限 | `legacy` |
| **G5 脱敏留痕**（**需批准保留策略**） | 新表、`transcript.py`、管理员 API、清理任务 | 敏感样例扫描 0 命中；过期被删；跨公司读 0；读取留审计 | 开关关闭 |
| **G6 备用和熔断** | 路由器第 5 步；复用 `CircuitBreaker` | 假供应商 5xx：切换并标注；恢复后回到主模型；Redis 挂了仍能调用 | 配置留空 |
| **G7 出站控制**（**需批准默认策略**） | `outbound.py`、公司策略、分级接入 | 标记字段请求中 0 出现；`internal_only` 无内部模型时拒绝；脱敏前后准确率报告 | 策略设为 `allow` |
| **G8 配额**（**改表**） | 新表；两处检查；`observe` → `enforce` | 并发压测不超额；死锁测试；超限 429 | `off` |
| **G9 账单核对** | 缓存计价、对账表和任务、告警 | 构造差异触发告警 | 关闭任务 |

**测试用假供应商：** `FakeProvider` 按脚本返回超时、429（带 `Retry-After`）、5xx、截断、空内容，全部不产生费用。这是 G4 和 G6 的基础。

**ADR-0001 后上表的变化（V 通过后生效）：**
- **G2：** 改为“按配置版本构造并缓存 Router”；请求仍然不可变。
- **G4：** 重试、`Retry-After`、退避交给 Router；自建部分是异常映射、回调逐次记账、预算改软上限（`MODEL_BUDGET_MODE=soft`）。上层网络重试照样删除。
- **G6：** 备用和冷却交给 Router，冷却状态放 Redis；不再复用 `CircuitBreaker`（V3 不通过时才复用）。
- **G8：** 仍自建，改为软上限（第 6 节）。
- **V1 或 V2 不通过：** 上表 G2、G4、G6 按原文执行，供应商调用改用 LiteLLM SDK（`num_retries=0`）。

---

## 10. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 查任意一次模型调用 | 看到配置档、提示词版本、实际模型、逻辑调用号 |
| 模拟一次超时 | 2 条记录，预算 `calls` 只加 1，费用保留 |
| 模拟 429 带 `Retry-After: 3` | 等约 3 秒再试 |
| 模拟持续 5xx | 熔断打开后快速失败，恢复后放行 |
| 模拟截断 | 明确错误码，不进入内容修复 |
| 任务运行中修改配置 | 该任务不受影响 |
| 改提示词不升版本 | CI 失败 |
| 公司超配额 | 建任务返回 429 |

**仍需开工时确认：** `nodes.py:262` 的 `semantic_review` 实际包含哪些调用；`reserve_local_resource_call` 对用途字段的影响；DeepSeek 的 JSON 模式、缓存和 `Retry-After` 实际行为要以官方文档和测试为准；`usage_quota_counters` 的 RLS 与后台任务的权限配合。
