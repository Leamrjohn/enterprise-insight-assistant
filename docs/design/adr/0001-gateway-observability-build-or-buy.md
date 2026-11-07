# ADR-0001 模型网关、观测、提示词版本：引入开源组件还是自建

**状态：** 已决定：方案 D，待第 5.1 节验证。验证结论写回 5.1 节之前，G4、G6 不开工。
**日期：** 2026-11-07
**范围：** 总计划工单 G1、G2、G4、G6、G8、G9、O1、O2。其余工单不受影响。

**依据标记：**
- 【代码】本次读代码查到的事实，没有运行。
- 【外部】来自网上资料，链接见第 9 节。本次没有安装或试用任何组件。

---

## 1. 为什么要做这个决定

总计划几乎每个模块都打算自建。企业里常见的做法是：通用基础设施用成熟组件，跟业务绑定的部分才自建。本 ADR 逐项判断：网关、观测、提示词这三块，哪些属于“通用”。

**判断尺子是现有的不变量**（来自[模型网关设计](../enterprise/04_model_gateway_prompts.md)和[观测设计](../enterprise/07_observability_operations.md)）。组件再好，违反其中任何一条都不能直接用：

| 编号 | 不变量 | 现在在哪里 |
|---|---|---|
| I1 | 每次**物理调用**之前先预占预算，失败不能当免费 | `deepseek.py:123` 的 `reserve_model_call`【代码】 |
| I2 | 价格、预算、模型配置随任务冻结，运行中不变 | `model_policy_snapshot`【代码】 |
| I3 | 回放找不到录音就直接失败，不会误付费 | `replay.py:60`【代码】 |
| I4 | 遥测不记录问题、回答、SQL、文档原文 | 观测设计第 3.2 节 |
| I5 | 配额检查和任务行在同一个数据库事务里，并发也不能超额 | 网关设计第 6 节 |

**I1 的放宽版本 I1′（方案 D 使用）：** 调用后记账加软上限。每次调用前检查“已结算费用 + 在途调用估算”是否低于上限，调用后按实际用量结算。最多超出“并发数 × 单次调用费用上限”。**“失败不能当免费”继续保留：** 超时等失败仍记为未知费用。I1 放宽后，I5 也随之变成软上限。

**现状（与本决定有关的）：** 用 openai SDK 直连 DeepSeek；网关是单例，切换备用模型时会改写共享状态（`deepseek.py:254`）；提示词是代码里的字符串常量（如 `knowledge/tool_agent.py:87`）；代码里没有 OpenTelemetry 或 Prometheus【代码】。

---

## 2. 候选组件

| 组件 | 是什么 | 许可 | 运行形态 | 需要注意 |
|---|---|---|---|---|
| **LiteLLM** | 统一 100 多家模型接口；Router 负责重试、备用、冷却；Proxy 负责虚拟密钥和预算 | 核心 MIT；`enterprise/` 目录是商业许可（标签预算、SSO 超过 5 人等）【外部】 | SDK 是 Python 库；Proxy 是独立服务，要自己的 Postgres | 2026-03-24 PyPI 上 1.82.7、1.82.8 被投毒，会窃取凭据【外部】 |
| **Langfuse** | LLM 调用链路、提示词版本、评测数据集 | 核心 MIT，`ee/` 目录付费【外部】 | 自部署 v3 需要 Postgres、ClickHouse、Redis、S3【外部】 | 2026-01 被 ClickHouse 收购，官方表示核心继续 MIT【外部】 |
| **OpenTelemetry** | 厂商中立的 trace、指标标准；有 FastAPI、Celery、SQLAlchemy、OpenAI 的自动埋点 | Apache 2.0 | Python 库加 Collector 容器 | GenAI 语义约定（`gen_ai.*`）至今全部是 Development 状态，2026-06 已移到独立仓库，名字还可能改【外部】 |

**未评估：** Portkey、Arize Phoenix、Opik。如果第 6 节的复评条件触发，再一起比较。

---

## 3. 逐项对照

| 工单 | 开源组件能提供什么 | 和不变量冲突吗 | 建议 |
|---|---|---|---|
| **G1 提示词注册表** | Langfuse：提示词版本、标签、运行时拉取、回滚 | **冲突 I2、I3。** 运行时可以改，就打破了“随任务冻结”；改了内容，回放键会变。提示词也不在 git 里，绕开了代码评审和 CI 评测门禁（E10） | **自建**：文件加 manifest（设计第 3 节）。把 `prompt_version` 作为 trace 属性发出，以后接任何平台都能看到 |
| **G2 不可变请求** | LiteLLM 的 `completion()` 每次调用都传全部参数，天然无状态 | 不冲突 | **自建**。两家供应商都是 OpenAI 兼容接口，openai SDK 已经够用；无状态的 `ProviderClient` 不到百行 |
| **G4 重试、错误分类** | LiteLLM Router：读 `Retry-After`（最多等 1 分钟）、按错误类型设重试次数、退避加抖动【外部】 | **冲突 I1。** Router 在内部重试，账本只看到 1 次调用，重试那次没有预占。要在它的回调里做预占，就得确认回调能拒绝发送；SDK 是否支持这一点没有查到 | **自建**，但**借鉴它的规则**：`Retry-After` 设上限；没有时从 0.5 秒退避到 8 秒并加抖动；按错误类型配置重试次数 |
| **G6 备用和熔断** | Router 的 fallback 和 cooldown | 部分冲突。冷却状态默认在进程内，多个 Worker 要另配 Redis；备用调用同样有 I1 的问题 | **自建**，复用已有的 Redis 熔断器 `CircuitBreaker`（`tool_guard.py:86`）【代码】 |
| **G8 公司和用户配额** | LiteLLM Proxy：按虚拟密钥、团队、用户设预算 | **冲突 I5。** 预算按虚拟密钥算，不按公司；是调用后记账，不是和任务行同一事务的原子预占；要多跑一个服务和一套库表；部分按团队的功能在企业版【外部】 | **自建**（设计第 6 节的条件更新） |
| **G9 计价和对账** | LiteLLM 内置价格表 | 冲突 I2：价格表随库版本变化，不随任务冻结。它是否处理 DeepSeek 缓存命中价，**没有查到** | **自建**价格表。可以拿它的价格数据做人工核对 |
| **O1 全链路 trace** | OTel SDK，加上 FastAPI、Celery、SQLAlchemy 的自动埋点 | 不冲突，前提是两点：OpenAI 自动埋点的“记录消息内容”开关保持关闭；`gen_ai.*` 属性名会变 | **引入**（观测设计已选）。`gen_ai.*` 属性名只在 `safe_span_attributes()` 一处出现，固定语义约定版本 |
| **O2 指标和看板** | Prometheus、Grafana、Alertmanager | 不冲突 | **引入**（观测设计已选） |
| **LLM 观测平台**（不对应现有工单） | Langfuse：按原文看每次调用、评测数据集、LLM 打分 | **冲突 I4。** 它最大的价值就是看原文；自部署还要 ClickHouse，和本机已有的 4 个 Postgres、ClamAV、LocalStack 抢内存 | **暂不引入。** Langfuse 能接收 OTLP，所以 O1 做完后可以把它当作另一个导出目标，只在开发环境、只接脱敏数据时再评估，几乎没有锁定成本 |

---

## 4. 对照后看到的事实

1. **冲突几乎都来自 I1 和 I5。** 预占式账本是这个项目最严格的设计，而主流网关都是“调用后记账”。这不是组件不好，而是两种设计目标不同：它们优先保证可用，本项目优先保证费用上限。
2. **OTel 没有冲突，而且是先做不会后悔的一步。** 有了 OTel 埋点，以后换 Tempo、Langfuse 还是 Phoenix，都只改导出配置。
3. **供应链风险跟“引入还是自建”无关，但引入会放大它。** LiteLLM 的投毒事件里，据报道官方 Docker 镜像因为锁了版本而未受影响【外部】。无论选哪个方案，**都要先做 E2（锁版本加哈希校验）**。
4. **I2 不禁止备用模型。** 冻结的是“这个任务能用哪些模型”的清单，备用链本身就在清单里。备用模型从未生效，是因为快照写死了空列表 `"fallback_models": []`（`workflow/repository.py:99`）【代码】。要启用备用，应该填清单（G6），并由 G7 决定能否发给第二家供应商。放弃 I2 会破坏 S4（每个任务可完整还原）和崩溃恢复后账本的一致性。
5. **目前唯一证实的预算耗尽，拦下的是循环 bug。** 任务 185：Data 被复核拒绝 → 重新规划 → 再跑 Data，共 8 次调用、$0.0056，因调用次数超限停止；当时结论是“上游原因未定位，不能据此增加预算”（`docs/worklog.md:199`）【记录】。所以预算上限要保留，担心“真实需要多花钱的任务跑不完”，应该靠 C2 的 token 分布基线把上限定准，或者在预算耗尽时进入明确终态、由人确认追加。

---

## 5. 方案

| 方案 | 内容 | 好处 | 代价 |
|---|---|---|---|
| **A 标准底座加自建核心** | OTel、Prometheus、Grafana 引入；网关路由、账本、配额、提示词、计价自建，借鉴 LiteLLM 的重试规则；写明复评条件 | 不变量全部保住；新依赖最少；核心模块正好是学习重点 | 路由器和错误分类要自己写、自己测，大约几百行加故障注入测试 |
| **B LiteLLM 只当适配层** | 在 A 的基础上，供应商调用改用 `litellm.completion(num_retries=0)`，重试、备用、账本仍由自己的路由器负责 | 以后加新供应商、本地模型时改动小 | 只有 2 家 OpenAI 兼容供应商时收益很小；多一个大依赖和供应链风险；回放键要确认不受影响 |
| **C 重度引入** | LiteLLM Router 管 G4、G6；Proxy 管 G8；Langfuse 管 G1 和 LLM trace | 写的代码最少；功能多 | 违反 I1、I2、I4、I5；要多跑 Proxy 和 Langfuse 两套服务（含 ClickHouse）；预算语义要重新设计 |
| **D Router 加软上限** | 在 A 的基础上：I1 改为 I1′；LiteLLM SDK 加 Router 负责 G4 的重试和 G6 的备用、冷却；**I2 保留**，按任务快照里的配置版本（如 `default/3`）构造 Router，同版本复用一个实例；价格表、G8 配额、G1 提示词仍然自建；Proxy 和 Langfuse 不用 | G4、G6 少写几百行代码和测试，重试规则用成熟实现；以后加供应商改动小 | 费用上限从硬变软（超出量见 I1′）；I5 也变软；多一个大依赖和供应链风险；R5 的训练工单 G2、G4 练习变少；**必须先通过第 5.1 节的验证** |

**放宽 I1 后各项冲突的变化（只对 D 适用）：**

| 部分 | 放宽前 | 放宽后 |
|---|---|---|
| Router 管重试、`Retry-After`（G4） | 内部重试没有预占 | 可以用：每次尝试调用后通过回调记账 |
| Router 管备用和冷却（G6） | 同上 | 可以用：冷却状态要放进 Redis，多个 Worker 共享 |
| I2 冻结 | 价格表随版本变化 | 不冲突：按快照的配置版本构造 Router，价格用自己的表 |
| Proxy 管公司配额（G8） | 不按公司、要多一个服务 | **仍不建议**：预算按虚拟 key 算，部分按团队的功能在企业版 |
| 回放（I3） | — | 要验证：回放层包在 LiteLLM 外面，整体替换调用 |
| 遥测不记原文（I4） | — | 配置问题：不打开它向外部平台上报的日志功能 |

**推荐 A 作为默认。** 理由：C 违反核心不变量；B 现在的收益抵不上新增的依赖和风险。**如果你接受软上限，D 是可行的替代**，但要等第 5.1 节的验证全部通过后，才替换 A 里 G4、G6 的部分；验证不通过就退回 A。

### 5.1 方案 D 的验证清单

**怎么做：** 单独的虚拟环境，用 LiteLLM 的模拟返回（`mock_response`）和假供应商注入超时、429、5xx、截断。不改项目依赖、不调真实模型、不花钱，预计半天。**引入这个依赖做验证也要先批准**（AGENTS.md）。

| # | 要确认的事 | 为什么重要 | 不成立时 |
|---|---|---|---|
| V1 | Router 内部的**每一次**重试和备用切换都会触发回调，并带上实际使用的模型名 | 账本才能记全每次物理调用 | D 不可用，退回 A |
| V2 | 能让 LiteLLM 和底层 SDK 完全不重试，只由 Router 控制 | 防止两层重试相乘 | D 不可用，退回 A |
| V3 | 在 Celery 多进程下同步调用 Router 正常；冷却状态能放进现有 Redis | 并发提高后行为一致 | 冷却改用现有 `CircuitBreaker`，只用 Router 的重试 |
| V4 | 回放网关能原样包在外面，录音的键不变 | 保住 I3，不误付费 | 改造回放层，或退回 A |
| V5 | 能从返回结果里拿到 DeepSeek 缓存命中的 token 数 | 计价准确（G9） | 自己从原始返回里解析 |

**验证完成的标准：** 每一项都有可重复运行的测试和结论；结果写进本节。

---

## 6. 复评条件（满足任一条就重新打开本 ADR）

| 条件 | 复评什么 |
|---|---|
| 供应商达到 3 家及以上，或者出现不兼容 OpenAI 接口的模型 | 方案 B（LiteLLM 当适配层） |
| 需要非开发人员在线改提示词 | Langfuse 的提示词管理；改动仍要过评测门禁、仍要冻结进任务快照 |
| G5 脱敏留痕加 `render_task_trace` 不够用，查一个问题超过 5 分钟 | Langfuse 或 Phoenix 作为开发环境的 OTLP 后端 |
| 多机部署，需要跨实例共享预算 | 网关服务化（自建服务或 Proxy） |
| OTel GenAI 语义约定发布 Stable 版本 | 按新名字迁移属性 |

---

## 7. 决定

我的是选择是方案D ，因为原先的条件1和条件2 的限制中 预占预算与主流调用后记账不同，而且前六个插件属于几乎无害的情况，litellm让项目可以调用多家模型，无需处理差异，router的重试和切换模型也适合本项目，然后proxy按公司或者团队区分在企业版，现有结构已经按照公司和员工区分，无需此功能，条件1改为软上限，因为当前只有一个worker，最多超出一次，条件2 可以保留，切换备用模型理由router和模型清单进行；然后验证不通过时：V1 或 V2 不通过，退到方案 B，只用 LiteLLM SDK（`num_retries=0`），重试和备用自建；V3 不通过，只用 Router 的重试，冷却改用现有的 `CircuitBreaker`。
---

## 8. 后果

### 8.1 工单变化

| 工单 | 原计划 | 选 D 之后 |
|---|---|---|
| **V（新增，排在 G4 前）** | — | 第 5.1 节 V1～V5 验证，不花钱。结论写回 5.1 节 |
| G1 提示词注册表 | 自建 | 不变 |
| G2 不可变请求 | 自建无状态 `ProviderClient` | 按快照里的配置版本构造 Router，同版本复用一个实例；请求仍然不可变 |
| G4 路由器、错误分类、重试 | 自建重试和退避 | 重试、`Retry-After`、退避交给 Router。**自建部分：** LiteLLM 异常映射到 `ModelErrorKind`；每次尝试调用后通过回调记账；预算语义改为 I1′（**改预算语义，需批准**，原计划已标注）；上层网络重试照样删除 |
| G6 备用和熔断 | 自建，复用 `CircuitBreaker` | 备用和冷却交给 Router，冷却状态放 Redis（V3）。快照里的备用清单要填，备用是谁仍要你决定，跨供应商要先过 G7 |
| G8 公司和用户配额 | 调用前原子预占 | 仍自建、不用 Proxy。改为软上限：调用前按估算检查，调用后结算累加 |
| G9 计价和对账 | 自建价格表 | 不变；缓存命中 token 从哪里取看 V5 |
| O1、O2 | OTel、Prometheus、Grafana | 不变 |
| B13 并发大于 1 | 演练和容量报告 | **新增前提：** 提高并发前，重新计算软上限最多超出多少（并发数 × 单次调用费用上限），写回本 ADR |

### 8.2 新增依赖（每个都要单独批准）

| 依赖 | 前提 |
|---|---|
| `litellm`（SDK 和 Router，不含 Proxy） | 先完成 E2：锁精确版本加哈希校验；不用 1.82.7、1.82.8 |
| `opentelemetry-*`（SDK、导出器、FastAPI、Celery、SQLAlchemy、OpenAI 埋点） | 记录消息原文的开关保持关闭 |
| Collector、Prometheus、Grafana、Alertmanager、Tempo 镜像 | 固定版本；放在 compose 的 `observability` profile |

### 8.3 要更新的文档

- [模型网关设计](../enterprise/04_model_gateway_prompts.md)：第 2.2 节调用流程、第 2.3 节错误分类、第 2.4 节预算规则、第 6 节配额、第 9 节落地步骤。
- [企业级总计划](../enterprise_plan_2026-11-05.md)第 7 节：G4、G6 的描述。
- [改造与学习路线](../../learning/build_and_learn_route_2026-11-07.md)第 6 节：R5 训练工单 G4 的内容，从“写重试”改为“写错误映射和回调记账，并完成 V1～V5”。

**已同步（2026-11-07）：** 三份文档都加了标注“ADR-0001”的段落，原文保留，作为 V1 或 V2 不通过时的退路。

### 8.4 接受的风险

- 费用上限从硬变软；并发为 1 时最多超出一次调用的费用。
- 多一个大依赖，有供应链风险。
- R5 里“亲手写重试”的练习变少，换成“验证第三方组件的行为”的练习。

---

## 9. 依据

**代码：** `backend/app/core/gateway/deepseek.py`、`backend/app/modules/runtime/tool_guard.py`、`backend/app/modules/runtime/context_budget.py`、`backend/app/modules/workflow/repository.py`、`backend/requirements/base.txt`。

**记录：** `docs/worklog.md:199`、`docs/smoke_results/20261031-round2-interrupted-summary.md`（任务 185 预算耗尽）。

**外部资料：**
- LiteLLM Router 的重试、备用、冷却规则：[docs.litellm.ai/docs/router/learn/reliability](https://docs.litellm.ai/docs/router/learn/reliability)、[配置默认值](https://docs.litellm.ai/docs/router/api_reference/configuration)
- LiteLLM 企业版功能：[docs.litellm.ai/docs/enterprise](https://docs.litellm.ai/docs/enterprise)
- LiteLLM 投毒事件：[NetSPI](https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/)、[ITPro](https://www.itpro.com/security/litellm-pypi-compromise-everything-we-know-so-far)
- Langfuse 被收购：[Langfuse 博客](https://langfuse.com/blog/joining-clickhouse)、[ClickHouse 博客](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability.md)
- Langfuse 自部署组件：[Railway 模板说明](https://railway.com/deploy/langfuse-v3)（第三方，开工前要以官方文档核对）
- OTel GenAI 语义约定状态：[Dash0](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained)、[DEV 文章](https://dev.to/azena-ai/opentelemetrys-genai-semantic-conventions-are-not-stable-yet-heres-what-actually-shipped-in-2026-3mke)
- OTel Python 自动埋点：[opentelemetry-python-contrib](https://opentelemetry-python-contrib.readthedocs.io/)

**没有核实的：** LiteLLM SDK 能否在调用前通过回调拒绝发送；LiteLLM 对 DeepSeek 缓存命中价的处理；Langfuse 自部署的官方硬件要求。
