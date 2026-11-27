# R3 工具调用链路讲解

**这份文档讲什么：** 一次工具调用从「节点决定要查数据」到「拿到 ToolOutput」经过的每一个函数。
**依据：** 源码现状（T1、T2、T3a、T3b、T3c、M1 骨架已落地）+ [工具平台设计](../design/enterprise/01_tool_platform.md) 的 R3 目标态。
**读法：** 第 1 节看全局，2～8 节按调用顺序逐层看，10 节看「还没做的」。每节末尾的「为什么」是这个设计的考量，读代码时最容易被忽略。

---

## 1. 全局：一条调用穿过 8 道关

```text
Worker 启动
  └─ tasks.py:778        ToolRuntime(db, attempt, context)        ← 整个任务只有一个
       └─ ToolGateway                                         ← 唯一入口
节点
  └─ build_toolset(node)  按名单造工具对象，包成 RuntimeTool
       └─ Toolset.call("sql_query", {...})
            └─ RuntimeTool.execute
                 └─ ToolGateway.call(name, params)             ← 名字→对象，唯一入口
                      └─ ToolRuntime.execute → pipeline.run
                          1 allowlist            任务快照允许这个工具吗
                          2 current_authorization 用户现在还是有效成员吗
                          3 input_schema          参数符合登记契约吗
                          4 scope                 公司/冻结文档范围对吗
                          5 document_visibility   文档现在还看得见吗
                          6 server_parameters     加模型不能传的运行时参数
                          7 budget                扣一次任务工具配额
                          8 execute               真执行 + 写审计
                               └─ SQLTool / RAGTool / GuardedTool / MCP 客户端
```

**关键点：** 8 个 stage 的顺序是硬约束。`pipeline.run` 会先比较 stage 名字列表和 `STAGE_ORDER`，不一致直接抛 `PipelineOrderError`，所以任何工具都没法跳过某一关，也没法把某一关挪到前面。

---

## 2. 第 0 层：建链（一个任务一次）

| 函数 | 位置 | 作用 | 输入 → 输出 |
|---|---|---|---|
| Worker 主流程 | `modules/workflow/tasks.py:778` | 任务受理时建一次运行时 | 任务记录 → `ToolRuntime` 放进 `workflow_kwargs` |
| `ToolRuntimeContext` | `modules/runtime/tool_runtime.py:53` | 冻结的调用上下文（不可变） | `task_id`、`company_id`、`allowed_document_ids` |
| `ToolRuntime.__init__` | `:121` | 校验 task 和 attempt 是同一个任务；建网关 | 不匹配直接 `ValueError` |
| `ToolGateway.__init__` | `:76` | 持有一个 `{name: Tool}` 注册表 | — |

**为什么一个任务只建一次：** `allowed_document_ids` 是受理时冻结的。之后文档被删、被改权限，这份冻结集合不变，由第 5 关再去数据库复核「现在还看不看得见」。冻结和实时复核是两件事，都必须有。

---

## 3. 第 1 层：节点 → 工具集

| 函数 | 位置 | 作用 |
|---|---|---|
| `_data_node` / `_knowledge_node` | `modules/workflow/orchestration/nodes/data.py:24`、`knowledge.py:18` | 调 `build_toolset`，再选 Agent 跑 |
| `build_toolset(node, state)` | `modules/workflow/orchestration/toolsets.py:109` | 本节点工具集的唯一构造处 |
| `tool_catalog()` | `toolsets.py:104` | 把登记表 + 模型可见工具合成一个 `ToolRegistry`，第一次调用就校验，坏声明直接启动失败 |
| `ToolRegistry.__init__` | `modules/runtime/tools/registry.py:78` | 调 `validate_definitions`，有错抛 `ToolRegistryError` |
| `validate_definitions` | `registry.py:16` | 9 条启动规则（重名、写操作、版本号、transport、角色非空、runtime 必须有 output_model 和 to_evidence…） |
| `_sql_query(state)` | `toolsets.py:52` | 造 `SQLTool`；只有模型自选路线才外包 `GuardedTool` |
| `_rag_search(state)` | `toolsets.py:78` | 按配置造 `RAGTool` / MCP 适配器 / `GuardedTool` + `FallbackTool` |
| `ToolRuntime.wrap(tool)` | `tool_runtime.py:135` | 登记进网关，返回 `RuntimeTool` |
| `ToolGateway.register(tool)` | `:80` | 按名字登记；同名覆盖（节点重跑时换新实例） |
| `Toolset.of(*tools)` | `modules/analysis/tool_protocol.py:67` | 包成不可变工具集 |

**为什么加工具只改 4 处：** 节点只认 `NODE_TOOLSETS` 里的名字（`toolsets.py:33`），Agent 只认 `toolset.call(name)`。新增只读工具 = 登记表加一条 + 实现函数 + 结果转换函数 + `NODE_TOOLSETS` 加名字，`nodes/` 和 Agent 一行不动。

---

## 4. 第 2 层：Agent 调用点

| 调用点 | 位置 | 说明 |
|---|---|---|
| `DataAgent.run` → `self._tools.call("sql_query", {"sql": ...})` | `modules/analysis/data/data_agent.py:323`、`:477` | 固定路线：Agent 自己生成 SQL，交给工具执行 |
| `KnowledgeAgent.run` → `self._tools.call("rag_search", parameters)` | `modules/knowledge/agent.py:149` | 固定路线检索 |
| `ToolCallingDataAgent` handler | `modules/analysis/data/tool_agent.py:403` | 模型自选路线：模型提议的调用进到这里 |
| `ToolCallingKnowledgeAgent` handler | `modules/knowledge/tool_agent.py:153` | 同上，文档检索 |
| `Toolset.call(name, params)` | `tool_protocol.py:76` | 未在工具集里的名字直接 `tool_unknown`，不往下走 |

**注意：** Agent 拿不到 `ToolRuntime`，只拿得到 `Toolset`。它没有能力绕过网关，这是「唯一入口」在类型层面的保证。

---

## 5. 第 3 层：ToolGateway（唯一入口）

| 函数 | 位置 | 作用 |
|---|---|---|
| `RuntimeTool.execute(input)` | `tool_runtime.py:114` | 适配旧 Tool 协议，转调 `gateway.call` |
| `ToolGateway.call(name, parameters)` | `:84` | ① 名字查不到 → `tool_unknown`；② 走空范围特殊路径；③ 否则 `runtime.execute` |
| `ToolRuntime.resolve_empty_document_scope(tool, input)` | `:139` | `rag_search` + `document_ids == []` 的授权内空集合：写 `knowledge_scope_empty` 事件，直接返回 `insufficient_evidence`，不执行检索 |
| `ToolRuntime._deny(tool, code, details)` | `:183` | 统一拒绝出口：写 `tool_denied` 事件 + 一条 denied 的 `ToolCallRecord` + 返回 `ToolOutput` |
| `deny_message(code)` | `:49` | 错误码 → 给模型看的中文说明（码是机器契约，文案是给人看的） |

**为什么空范围要单独一条路径：** 「这个任务本来就没有可查文档」是正常业务结果，不是拒绝。如果走正常流水线，第 6 关会因为冻结集合为空而拒绝，任务就变成失败。所以这里在进入流水线前先分辨：**空集合 + 授权通过 = 证据不足；空集合 + 授权不过 = 拒绝**。两者不能混。

---

## 6. 第 4 层：ToolRuntime.execute → pipeline（8 道关）

### 6.1 外壳

| 函数 | 位置 | 作用 |
|---|---|---|
| `ToolRuntime.execute` | `tool_runtime.py:391` | 开 `tool.<name>` span，调 `_execute`，把结果写进 span |
| `ToolRuntime._execute` | `:405` | `pipeline.run(self._stages(), ToolCall(tool, input))` |
| `ToolRuntime._stages` | `:408` | 返回 8 个 `(名字, 函数)` |
| `pipeline.run(stages, call)` | `modules/runtime/tools/pipeline.py:32` | 校验顺序 = `STAGE_ORDER`，逐个跑；某关返回非 None 就停 |

### 6.2 逐关

| # | stage 函数 | 位置 | 做什么 | 失败码 / 分类 |
|---|---|---|---|---|
| 1 | `_stage_allowlist` | `:420` | 从任务快照读 `ToolPolicy`，名字必须在 `allowed_tools` 里 | `tool_not_allowlisted` / DENIED |
| 2 | `_stage_current_authorization` → `_validate_current_authorization` | `:426` → `:235` | 查定义里的 `allowed_roles`，调 `current_member_allowed` | `tool_current_authorization_denied` / DENIED |
| 3 | `_stage_input_schema` → `_validate_input` | `:429` → `:305` | 用登记表的 `input_model` 校验并归一化参数 | `tool_input_schema_invalid` / CALLER |
| 4 | `_stage_scope` → `_validate_scope` | `:436` → `:209` | 公司必须是当前任务的；`rag_search` 的文档必须是冻结集合子集 | `tool_company_scope_*`、`tool_document_scope_denied` / DENIED |
| 5 | `_stage_document_visibility` → `_validate_current_document_scope` | `:440` → `:289` | 查库确认每篇文档现在仍对公司内该角色可见 | `tool_document_current_authorization_denied` / DENIED |
| 6 | `_stage_server_parameters` → `_with_server_parameters` | `:443` → `:329` | 记下模型原始参数名（审计用），再加 `_runtime_*` 参数 | 不会失败 |
| 7 | `_stage_budget` → `_reserve_call` | `:449` → `:375` | `SELECT … FOR UPDATE` 锁任务行，比总配额和单工具配额，通过就 +1 | `tool_budget_exhausted` / EXHAUSTED |
| 8 | `_stage_execute` | `:452` | 写 `tool_started` → 调工具 → 结果校验 → 写 `tool_completed`/`tool_failed` + `ToolCallRecord` | 见下 |

**第 8 关内部顺序：**

1. `append_workflow_event(tool_started)` + commit
2. `tool.execute(input)` —— 真的执行
3. 捕获 `ModelBudgetExceeded` / `ModelCallCancelled` → 记 receipt 后**重新抛出**（整个任务要停）
4. 捕获其它异常 → `tool_runtime_unexpected_error`（不记录异常正文）
5. `_with_evidence(tool, result)`（`:350`）：`output_model.model_validate` 校验结构，再 `to_evidence` 转成统一 `Evidence`
6. 写 `tool_completed`/`tool_failed` + `ToolCallRecord`，commit
7. 若第 3 步捕获了停止信号，现在再抛

### 6.3 辅助函数

| 函数 | 位置 | 作用 |
|---|---|---|
| `ToolRuntime._task()` | `:369` | 取任务；取不到说明数据被删，抛 `RuntimeError` |
| `_tool_contract_version(tool)` | `:178` | 审计里记的契约版本，从登记表来 |
| `_runtime_mcp_context(input)` | `:250` | 生成给服务端的签名绑定：task、execution、actor、角色、公司、文档范围哈希 |
| `current_member_allowed` | `tools/authorization.py:15` | 用户启用 + 成员 approved + 角色在允许集 |
| `documents_still_visible` | `tools/authorization.py:37` | 每篇文档在同公司且 `min_view_role` 允许 |

**为什么权限在第 2 关、参数在第 3 关：** 先确认「你是谁、你还配不配」，再谈「你传了什么」。反过来的话，一个已被撤权的人能通过错误信息探到工具的参数契约。

**为什么配额在第 7 关而不是第 1 关：** 只有前面全部通过才扣。参数写错的调用不该消耗任务额度，否则模型乱试几次就把配额烧光。

**为什么重试不重复扣配额：** 配额记的是「逻辑调用次数」，重试属于同一次逻辑调用。

---

## 7. 第 5 层：真正执行的工具

| 实现 | 位置 | 执行路径 |
|---|---|---|
| `SQLTool.execute` | `modules/analysis/data/sql_tool.py:36` | → `validate_sql`（AST 校验）→ `execute_readonly_sql`（`sql_executor.py:94`，只读事务 + `statement_timeout`） |
| `RAGTool.execute` | `modules/knowledge/tool.py` | → 向量检索 + 重排，返回 `status/evidences` |
| `GuardedTool.execute` | `modules/runtime/tool_guard.py:157` | 先问熔断器；执行；INFRA 失败按退避重试；最后 `record_failure` / `record_success` |
| `CircuitBreaker.before_call` | `tool_guard.py:92` | 返回 `closed` / `probe` / `open`；Redis 挂了就放行（它保护工具，不是安全控制） |
| `FallbackTool.execute` | `tool_guard.py:192` | 主工具挂或熔断 → 换备用（MCP 挂了回退本地 RAG） |
| `McpEvidenceReadTool.execute` | `modules/knowledge/mcp_adapter.py:226` | 老的 stdio 适配器，当前工具集用的是它 |
| `call_tool` / `_call` | `modules/runtime/tools/mcp_client.py:31` / `:52` | 新的 HTTP 服务客户端：签名上下文 + 服务名 + 超时；任何传输失败统一成 `mcp_transport_unavailable` |

**注意现状：** `mcp_client.py` 和 `tool_service/server.py` 是 M1 落地的新服务骨架，但 `toolsets.py` 还没切过去（`_rag_search` 仍用 `McpEvidenceReadTool.stdio()`）。`definition.ALLOWED_TRANSPORTS` 现在只有 `{"in_process"}`，M2 才放开 `mcp`。

---

## 8. 第 6 层：MCP 服务端（跨进程的第二次校验）

| 函数 | 位置 | 作用 |
|---|---|---|
| `create_tool_server(...)` | `backend/app/tool_service/server.py:144` | 建 `MCPServer`，把每个工具注册成 MCP tool |
| 内部 `call(arguments, context, signature)` | `:155` | 开数据库会话 → `authorize` → 工具的 `check` → `_reply(tool.run(...))` |
| `authorize(db, raw_context, signature, key, now)` | `:118` | 验签 → 设租户作用域 → 查任务（公司、发起人、`active_execution_id` 一致）→ 复核成员资格 |
| `_parse_context(raw)` | `:107` | 字段集合必须完全一致，否则按签名无效处理 |
| `verify(context, signature, key, now)` | `tools/context.py:78` | 先验 HMAC，再验过期（顺序不能反） |
| `_canonical(context)` / `sign` | `context.py:68` / `:74` | 排序键 + 固定分隔符，两边必须签出同样的字节 |
| `check_rag_scope(db, ctx, args)` | `server.py:55` | 公司一致 → 文档清单哈希与签名一致 → 文档现在仍可见 |
| `document_scope_sha256` | `context.py:58` | 把「公司 + 文档清单」绑成一个哈希，清单顺序无关 |
| `_reply(result)` | `:97` | `ToolOutput` → `{success, data}` 或 `{success, error_code}` |
| `_rag_search` / `_rag_tool` | `:85` / `:77` | 进程内只建一次 RAGTool（模型加载贵） |

**为什么要验两次：** 客户端（Worker）验的是「此刻这个用户还能不能用这个工具」，服务端验的是「这个请求真的来自那个 Worker，且公司/文档范围没被改」。任何一边单独放行都不够——客户端被绕过时服务端还在，服务端配置错时客户端还在。这叫纵深防御。

**为什么签名不是权限：** HMAC 证明「谁发的」，不证明「他现在还有权」。所以服务端验完签还要回库查成员资格和文档可见性。签名只管传输层不可篡改，授权永远以数据库当前状态为准。

---

## 9. 错误分类：一个码决定「下一步怎么办」

| 函数 | 位置 | 作用 |
|---|---|---|
| `classify(code)` | `tools/errors.py:70` | 错误码 → `ErrorClass`；**未登记的码按 INFRA** |
| `ErrorClass` | `errors.py:7` | CALLER / DENIED / INFRA / EXHAUSTED / TASK_STOP |
| `is_infrastructure_failure(output)` | `tool_guard.py:25` | 只有 INFRA 才算「工具挂了」，才计入熔断 |
| `outcome_of_failure(output)` | `tool_guard.py:33` | 转成循环里的 `denied/exhausted/unavailable/repairable` |

**为什么未登记的码算 INFRA：** 一个没人命名的失败，不能当成「模型能自己修」的错误交回去。默认最保守：当作依赖故障，重试一次，然后明确失败。反过来（默认 CALLER）会让模型对着一个基础设施故障反复改参数。

**为什么权限类永不重试：** 换个参数、重试一次都改变不了「你不是这家公司的人」。

---

## 10. 模型自选工具循环（T8 / T9，默认关闭）

| 函数 | 位置 | 作用 |
|---|---|---|
| `run_tool_loop(...)` | `modules/runtime/tool_loop.py:168` | 主循环：调模型 → 解析参数 → 交给 handler → 按 outcome 决定继续/停止 |
| `_call_model` | `:151` | 只对 `RetryableModelError` 按退避重试 |
| `_parse_arguments(call, spec)` | `:129` | JSON 解析 + `input_model` 校验，失败转成 `repairable` 回复 |
| `ToolSpec.from_definition` | `:52` | 模型看到的说明只从登记表生成，不允许第二份拷贝 |
| `ToolSpec.to_openai` | `:68` | 渲染成 function calling 的 schema |
| `LoopLimits` | `:98` | 轮数、调用数、修复次数、秒数、模型重试，全从 `TOOL_LOOP_*` 配置来 |
| `LoopResult` / `ToolReply` | `:112` / `:85` | 循环结果 / handler 的决定（内容 + outcome + 错误码） |
| `_STOP_ON_OUTCOME` | `:121` | `finish/denied/exhausted/unavailable` 立即结束循环 |

**循环里谁说了算：** 模型只提议。参数校验、权限、范围、SQL 校验、配额全在 handler 和 ToolRuntime 里，模型改不了。循环的上限也全是代码常量，不是提示词。

**R3 完成后 T8 还要加：** 把循环消息接进上下文引擎（超预算就停）、大结果换成 `result_id` 句柄（`read_result` 分页读，且不能跨任务）。

---

## 11. 现状 vs R3 完成后：13 步对照

设计稿第 3 节列了 13 步。现在落地成 8 个 stage，缺口如下：

| 设计步骤 | 现在在哪 | 状态 |
|---|---|---|
| 1 登记 | 网关名字查找 + `_validate_input` 里的定义查询 | 有，未独立成 stage |
| 2 策略 | `_stage_allowlist` | 有 |
| 3 取消检查 | 无（取消在模型治理层判断） | **缺** |
| 4 当前权限 | `_stage_current_authorization` | 有 |
| 5 参数校验 | `_stage_input_schema` | 有 |
| 6 范围绑定 | `_stage_scope` | 有 |
| 7 服务端参数 | `_stage_server_parameters` | 有 |
| 8 配额预占 | `_stage_budget` | 有 |
| 9 熔断判断 | `GuardedTool`，只在模型自选路线 | **T6 移进流水线**（主链也要有） |
| 10 执行 + 超时重试 | `_stage_execute` + 工具自身超时 + `GuardedTool` 重试 | **T4/T5 补齐** |
| 11 结果校验 | `_with_evidence` | 有 |
| 12 大小控制 | 无 | **T5** |
| 13 审计 | `_deny` 与 `_stage_execute` | 有，但一次逻辑调用一条；**T4 改成每次尝试一条 + `logical_call_id`** |

其余 R3 工单的插入点：

- **T4**：`ToolCallRecord` 加 `logical_call_id`、`attempt_no`、`error_class`、`catalog_hash`；重试移进流水线，每次尝试一条审计。
- **T5**：`timeout_ms × 1.5` 超时告警；`on_overflow` 截断或拒绝。
- **T7**：`allowed_roles` 换成权限名（`data:query`），加角色→权限表。
- **M2/M3**：`ALLOWED_TRANSPORTS` 加 MCP；`_stage_execute` 按 `definition.transport` 分发；`sql_query`、`template_query` 迁到服务端，SQL 校验在服务端再跑一遍。
- **T8/T9**：循环 v2、结果句柄、按确定性分流。
- **T10**：`template_query` 接进固定路线。
- **T13/T11c/T11d**：写工具审批框架，登记表才放开 `side_effect="write"`。

---

## 12. 为什么是这个顺序（设计考量汇总）

1. **能拒绝的关越靠前越好**：身份 → 参数 → 范围，都在花任何资源之前。
2. **静态判断先于查库**：第 4 关比的是内存里的冻结集合，第 5 关才查数据库。便宜的在前。
3. **配额最后扣**：前面任何一关失败都不该消耗额度。
4. **执行与审计同一关**：`tool_started` 在执行前写，`tool_completed` 在执行后写，中间无论抛什么都有记录。
5. **审计失败不许返回数据**：宁可任务失败，不能出现「有结果、无记录」。
6. **冻结 + 实时两套范围**：冻结防中途被改范围，实时防中途被撤权。
7. **签名只证来源，不证权限**：所以服务端还要回库复核。

---

## 13. 怎么用这份文档读代码

1. 先只看第 1 节的图，把 8 个 stage 名字背下来。
2. 打开 `tool_runtime.py`，只找 `_stages()`，对照第 6.2 节的表，确认顺序。
3. 随机挑一关，问自己「删掉它会怎样」——答案就是它防的那个坏情况。
4. 再挑一件 R3 还没做的事（比如第 12 步大小控制），想一下你会插在哪一关、插进去要改哪几个函数。**这就是盲设计练习。**
