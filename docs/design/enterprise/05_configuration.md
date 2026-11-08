# 配置体系实现设计

**状态：** 设计稿，未实现。文中代码和 SQL 是草案。对应总计划工单 K1～K4。

**配置的来源只有四层：** 代码默认值 → 环境 → 公司策略 → 任务快照。**公司策略只能收紧平台上限，不能放宽。**

---

## 1. 现在怎么运行

```text
启动    Settings() 从 backend/.env 和环境变量读取（settings.py:18）
        get_settings() 用 lru_cache 缓存（:329），改配置要重启
使用    21 个文件调用 get_settings()，各自取字段
建任务  workflow/repository.py:94-109 把部分配置复制进任务快照
        workflow_policy / model_policy / model_budget / tool_policy / tool_budget
运行    Worker 按快照执行；部分配置仍读全局（如温度，deepseek.py:71）
凭据    数据源密码：os.environ.get(source.credential_env_var)（sql_executor.py:185）
```

**要保留的好设计：** 客户端不能提交预算（`model_budget.py:13`）；策略随任务冻结；生产环境拒绝默认 JWT 密钥（`settings.py:131`）；配置有组合校验（`:177-189`）；`SecretStr` 防止日志泄露。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| 约 87 个字段平铺 | `settings.py:18-121` | 上传、数据库、模型混在一起，难查难审 |
| `extra="ignore"` | `settings.py:23` | 写错配置名不报错，默认值悄悄生效 |
| 业务限额写死在代码 | 见第 3 节 | 不能按公司调整，也不在任务快照里 |
| 无公司级配置 | `Company` 只有 id、name、created_at（`organizations/models.py:23`） | 灰度只能用全局 `model_tool_company_ids` |
| 快照不完整 | 温度、上下文预算、RAG 参数没有冻结 | 恢复后行为可能变化 |
| `.env.example` 靠手工维护 | 约 77 键，少于字段数 | 新人不知道该配什么 |
| 数据源凭据由租户指定环境变量名 | `organizations/schemas.py:49` | **安全问题**，见 `06_security_identity.md` 第 2 节 |

---

## 2. 目标结构

```text
backend/app/core/config/
    base.py         公共校验、严格模式
    app.py          AppConfig：环境、日志、CORS
    infra.py        InfraConfig：数据库、Redis、对象存储
    security.py     SecurityConfig：JWT、限流、登录保护、出站
    model.py        ModelConfig：配置档选择、价格、预算上限
    tool.py         ToolConfig
    context.py      ContextConfig
    memory.py       MemoryConfig
    rag.py          RagConfig
    artifacts.py    上传（冻结，不改行为）
    flags.py        FeatureFlags
    settings.py     Settings：组合以上各域
    resolver.py     PolicyResolver：环境 + 公司策略 → EffectivePolicy
    catalog.py      配置清单：生成文档和示例文件
```

**环境变量名不变。** 运维不用改 `.env`。代码中逐步从 `settings.rag_retrieval_top_k` 改成 `settings.rag.retrieval_top_k`；迁移期间 `Settings.__getattr__` 兼容旧写法并在测试中告警，迁完后删除。

### 2.1 严格模式

不能简单改成 `extra="forbid"`：所有配置共用一个 `.env`，各域都会读到别人的键。改为启动后统一检查：

```python
def check_unknown_keys(settings, env_file_keys, environ) -> list[str]:
    declared = catalog.all_env_names()
    # .env 里的键必须全部已声明；进程环境只检查项目前缀，PATH 等不管
    candidates = env_file_keys | {k for k in environ if k.startswith(PROJECT_PREFIXES)}
    return sorted(candidates - declared - catalog.dynamic_names())
```

| 环境 | 发现未知键时 |
|---|---|
| `production` | **启动失败**，错误里列出键名（绝不打印值） |
| `development`、`test` | 警告日志；CI 里按失败处理 |

### 2.2 配置清单

每个配置项声明这些信息，文档和 `.env.example` 由此生成：

```python
ConfigItem(
    env="RAG_RERANK_TOP_K", type=int, default=3,
    domain="rag", secret=False,
    description="重排后保留的片段数",
    bounds=(1, 20),
    company_override="tighten_max",  # no / tighten_max / tighten_min / subset / free
    frozen_in_task=True,
    restart_required=True,
)
```

**命令（目标形态）：**

```bash
python -m app.core.config.catalog --check
```

CI 运行时，如果 `.env.example` 和清单不一致就失败。

---

## 3. 代码常量迁移表

这些都是已读到的真实常量。K1 归入配置，**默认值不变，行为不变**。

| 常量 | 现在位置 | 新配置 | 能否按公司收紧 |
|---|---|---|---|
| `MAX_CONTEXT_TOKENS` 2048 等 | `conversations/service.py:423-430` | `context.history_*` | 否 |
| `COMPRESS_AT` 0.8、`MAX_ROWS…`、`MAX_CHUNK…` | `context_budget.py:21-23` | `context.*` | 否 |
| `EVIDENCE_REVIEW.budget_tokens` 4000 | `context_budget.py:151` | 策略文件 | 否 |
| `MAX_PLANNER_MEMORY_TOKENS`、TTL、保留期 | `memory/service.py:19-25` | `memory.*` | TTL 可缩短 |
| `LoopLimits` 6/8/2/90 | `tool_loop.py:76-82` | `tool.loop_*` | 可收紧 |
| `ToolBudget` 12/6 | `runtime/schemas.py` | `tool.budget_*` | 可收紧 |
| 超时 10000ms | `ToolPolicy` | 工具目录 | 可收紧 |
| `CircuitBreaker` 5/60/30/30 | `tool_guard.py:99-102` | 工具目录 | 否 |
| `MAX_PLANNER_ATTEMPTS`、`MAX_DATA_ATTEMPTS` 2 | `planning.py:18`、`data_agent.py:25` | `model.*` | 否 |
| `RRF_K` 60 | `rag/retrieval.py:17` | `rag.rrf_k` | 否 |
| 提示词证据 3000 字 | `rag/engine.py:52`【记录】 | 迁到上下文策略 | 否 |
| `RATE_LIMIT_MAX` 100、窗口 60 | `middleware.py:16-17` | `security.rate_*` | 可收紧 |

---

## 4. 公司策略

```sql
CREATE TABLE company_policies (
  id serial PRIMARY KEY,
  company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  version integer NOT NULL,
  policy jsonb NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'active',  -- active / superseded
  created_by integer REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, version)
);
CREATE UNIQUE INDEX uq_company_policy_active
    ON company_policies (company_id) WHERE status = 'active';
-- 开启并强制 RLS
```

```json
{
  "budget": {"max_cost": "0.05", "max_total_tokens": 8000},
  "memory": {"ttl_days": 7, "enabled_layers": ["fact"]},
  "tool": {"max_calls": 6},
  "egress_policy": "masked",
  "quota": {"monthly_cost": "100", "user_daily_cost": "5"},
  "flags": {"glossary": true}
}
```

### 4.1 合并规则（`PolicyResolver`）

| 规则 | 含义 | 例子 |
|---|---|---|
| `tighten_max` | `min(平台值, 公司值)` | 平台 `max_cost=0.15`，公司 0.05 → 0.05；公司 0.5 → **拒绝保存** |
| `tighten_min` | `max(平台值, 公司值)` | 最短密码长度 |
| `subset` | 取交集 | `enabled_layers`、可选模型 |
| `free` | 公司自选 | 启用的功能标记（平台已开放的范围内） |
| `no` | 公司不能设置 | 平台基础设施项 |

**保存时校验（API 返回 422），解析时再校验一次。** 平台上限下调后，旧策略也不能超过新上限。

### 4.2 任务快照

```text
建任务 → PolicyResolver.resolve(company_id)
      → EffectivePolicy（不可变，无密钥）
      → 现有 5 个快照列写入对应部分（不新增重复来源）
      → 新增 config_snapshot jsonb：context、memory、rag、flags、版本
      → config_snapshot_hash = sha256(规范化 JSON)
```

**节点从快照读，不再调用 `get_settings()` 取业务参数。** 基础设施配置（数据库地址等）仍读 `get_settings()`。

**恢复和重试：** 用同一份快照。回滚用现有的 `workflow_version_override` 机制（`lifecycle/versioning.py`），它已经保证原快照不变。

---

## 5. 功能开关和紧急开关

| 类型 | 决定时机 | 例子 | 存放 |
|---|---|---|---|
| **功能开关** | 建任务时决定，写入快照 | `glossary`、`conversation_state`、`model_tool_mode` | 环境 + 公司策略 |
| **紧急开关** | 运行时立即生效 | 停用某工具、停用某模型 | Redis，读取缓存 10 秒 |

**紧急开关只能“关”，不能扩大权限。** Redis 不可用时使用上一次缓存的值；启动时没有缓存就按“未关闭”处理，错误写日志。

**灰度例子：** 给公司 12 打开术语：

```text
公司策略 flags.glossary=true（新版本）→ 审计事件
新任务快照 flags.glossary=true → 使用
进行中的任务 → 不受影响
出问题 → 新版本策略改回 false，或用紧急开关
```

---

## 6. 密钥

```python
class SecretProvider(Protocol):
    def get(self, reference: str) -> SecretStr: ...

class EnvSecretProvider:
    """只允许平台预先声明的引用，租户不能指定任意环境变量。"""
```

| 规则 | 说明 |
|---|---|
| 平台密钥 | `JWT_SECRET`、`DATABASE_PASSWORD`、`DEEPSEEK_API_KEY` 等只由 `Settings` 读取 |
| 数据源凭据 | 只能用 `DS_CRED_` 前缀的引用，见安全设计 |
| 默认密钥 | 除 `development`、`test` 外一律启动失败；不再只检查 `production` |
| 日志 | 启动日志只打印键名和“已设置 / 未设置” |
| 轮换 | 上线级接密钥服务；本机级提供双 JWT 密钥（新旧并存）流程和演练 |

---

## 7. 失败路径

| 场景 | 系统行为 |
|---|---|
| 配置值超界或组合不合法 | 启动失败，错误列出键名和原因 |
| `.env` 有未知键（生产） | 启动失败 |
| 读取公司策略失败 | 建任务返回 503，不用默认值替代（否则可能放宽限制） |
| 公司策略内容不合法 | 拒绝保存；已保存的历史内容解析失败时同上 |
| 平台上限下调 | 解析时按新上限收紧 |
| Worker 和 API 配置不一致 | 任务用快照，不受影响；健康检查比较 `config_hash` 并告警 |
| 快照缺字段（旧任务） | 用旧任务创建时的默认值表，写事件，不用当前值 |

---

## 8. 落地步骤

每个工单一个提交。**验证命令是计划，尚未运行。**

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **K1 分域和常量归位** | 新增 `core/config/`；`Settings` 组合；迁第 3 节常量；兼容 `__getattr__` | `python -m pytest tests/unit/system/test_settings.py -x -q`；全量单元；**断言每个默认值和迁移前相同**；冒烟 | revert |
| **K2 严格校验和生成** | `catalog.py`、`check_unknown_keys`、生成 `.env.example`；CI 加检查；放宽默认密钥规则 | 写错配置名启动失败（测试）；示例文件和清单一致 | revert |
| **K3 公司策略**（**需批准：改表**） | 新表、`resolver.py`、管理 API（`require_owner`）、审计 | 每种合并规则的表驱动测试；不能放宽；跨公司读 0 | 无策略时等于平台默认 |
| **K4 快照哈希**（**改表**） | `analysis_tasks` 增 `config_snapshot`、`config_snapshot_hash`；节点改读快照 | 任务运行中改配置不影响该任务；任意任务可查生效值；恢复后相同 | 字段可空，旧路径保留一个版本 |

**K1 拆分提醒：** 21 个文件可能超过单工单上限（10 个文件）。按配置域分批迁移：先 RAG，再上下文，再记忆，依此类推。

---

## 9. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| `.env` 把 `RAG_RERANK_TOP_K` 拼错 | 生产模式启动失败 |
| 公司把 `max_cost` 设高于平台 | 422 拒绝 |
| 任务运行中改配置或策略 | 该任务行为不变 |
| 查任务 | 能看到生效值和哈希，无密钥 |
| 新增配置项不写清单 | CI 失败 |
| 全量密钥扫描 | 快照、日志、事件中 0 命中 |

**仍需开工时确认：** `Settings` 被 `db/session.py:7` 在导入时读取，分域时要避免循环依赖；`ACME_DEMO_DATABASE_PASSWORD` 这类动态键要迁成 `DS_CRED_`，并同步测试数据和 `docker-compose.yml`；紧急开关是否值得单独做，可以等第一次确实需要时再实现。
