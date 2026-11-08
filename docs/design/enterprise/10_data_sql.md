# Data 和 SQL 实现设计

**状态：** 设计稿，未实现。文中代码和 SQL 是草案。对应总计划工单 B3、B4。

**不变的约束：** 经营库只读；所有 SQL 必须过 Schema 和 AST 校验；不接受用户原始 SQL；查询限定在当前公司数据源内。**改 SQL 校验逻辑要先批准。**

---

## 1. 现在怎么运行

```text
data_node        nodes.py:560  创建 DataAgent，传公司数据源和快照
SQL 生成         sql_generation.py:307  模型写 SQL + query_contract
契约差集         data_agent.py:184  required_concepts 对比规划要求
SQL 语义复核     data_agent.py:221  模型判断
指标评估         data_agent.py:273  assess_metric_query（代码）
工具执行         data_agent.py:304 → ToolRuntime → validate_sql → 只读执行
结果评估         data_agent.py:311  assess_query_result、assess_numeric_assertion
证据             data_agent.py:324  rows + 三种评估结果
```

**要保留的好设计：** 多层 SQL 校验（54 种攻击全拦【记录】）；每公司一份冻结快照；查询成功不等于能回答（`query_contract.py:1`）；放行错误数字为 0【记录】；用 `replay_validated_sql` 重放已校验语句，不重新生成。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| **业务含义写死在代码，只适合演示库** | `metric_catalog.py:1` 注明“演示数据源”；`semantic_catalog.py:18`；`schema_selection.py:18` 的 `TABLE_TERMS`；`facts.py:5` | **换一家公司就没有指标定义和中文术语**，无法真正多租户 |
| 指标 SQL 也由模型自由写 | `sql_generation.py:346` | 已知指标也有波动和修复调用 |
| 概念比较靠字符串 | `data_agent.py:28` 只去掉几个后缀 | “销售额”和“营收”可能判为不一致，任务失败 |
| 过度拦截 | 19 题 4 题正确 SQL 被拦【记录】 | 答不出本该能答的问题 |
| `template_query` 用默认业务库凭据 | `sql_executor.py:54-69`；还在默认白名单（`workflow/models.py:137`） | 潜在跨公司风险；主链没用到 |
| 只取前 5 行做事实 | `facts.py` 的 `rows[:5]` | 多行结果的事实不完整 |
| 没有查询成本控制 | 只有超时和行数上限 | 大查询占满经营库连接，直到超时 |
| 表结构变化没有联动 | 只有快照指纹 | 字段改名后指标定义悄悄失效 |

---

## 2. 目标：语义层 + 指标优先

```text
问题 → 规划 → 语义层命中？
             ├ 是 → 模型只填 MetricQuery → 代码生成 SQL ┐
             └ 否 → 模型写 SQL（现有路径）──────────────┤
                                                       ↓
                                     validate_sql（两条路径都要过）
                                                       ↓
                                               只读执行 → 评估 → 证据
```

**为什么这样设计：** 已知指标的口径（比如“销售额只算已交付”）不该靠模型每次重新写对。模型只负责理解问题，SQL 由代码生成，结果稳定且省钱。未知问题仍走现有路径，能力不减。

**校验不跳过：** 代码生成的 SQL 同样要过 `validate_sql`，防止语义层配置本身有错。

### 2.1 语义层存储

```sql
CREATE TABLE semantic_models (
  id serial PRIMARY KEY,
  company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  data_source_id integer NOT NULL REFERENCES business_data_sources(id) ON DELETE CASCADE,
  schema_snapshot_id integer NOT NULL REFERENCES schema_snapshots(id),
  version integer NOT NULL,
  definition jsonb NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'draft',  -- draft/approved/retired
  created_by integer, approved_by integer,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (data_source_id, version)
);
-- 开启并强制 RLS
ALTER TABLE analysis_tasks ADD COLUMN semantic_model_id integer;  -- 随任务冻结
```

```json
{
  "tables": {
    "sales_orders": {
      "description": "销售订单事实表",
      "terms": ["订单", "销售", "下单", "交付"],
      "columns": {"status": {"values": {"delivered": "已交付"}}}
    }
  },
  "joins": [["sales_orders.customer_id", "customers.id"]],
  "metrics": {
    "revenue/v1": {
      "display_name": "销售额",
      "aliases": ["营收", "收入"],
      "unit": "CNY",
      "aggregate": {"function": "SUM", "column": "sales_orders.total_amount"},
      "time_column": "sales_orders.order_date",
      "mandatory_filters": [["sales_orders.status", "=", "delivered"]],
      "dimensions": {
        "region": {"column": "customers.region_code", "via_join": true},
        "month": {"expression": "date_trunc", "column": "sales_orders.order_date"}
      },
      "rounding_scale": 2
    }
  },
  "sensitive_columns": ["示例表.示例敏感字段"]
}
```

**这替换的硬编码：**

| 现在 | 迁到 |
|---|---|
| `METRIC_DEFINITIONS`（`metric_catalog.py:46`） | `metrics` |
| `BUSINESS_TABLES`（`semantic_catalog.py:18`） | `tables` |
| `TABLE_TERMS`（`schema_selection.py:18`） | `tables.*.terms` |
| `FILTER_VALUE_DEFINITIONS` | `columns.*.values` |
| `_COLUMN_DISPLAY_NAMES`（`facts.py:5`） | `columns.*.display_name` |

**现有演示定义转成种子数据，** 内容不变，保证回放和评测的基线可比。

### 2.2 语义层生命周期

```text
发现表结构（现有 discover）→ 生成草稿（表和字段，无业务含义）
→ 管理员补充指标、术语、敏感字段
→ 校验：引用的表和字段都存在；mandatory_filters 合法；能编译出通过 validate_sql 的 SQL
→ 另一位管理员批准 → 生效（新任务用，进行中的任务不变）
```

**表结构变化：** 重新发现时指纹不同 → 比对语义层引用 → 引用失效的指标标记 `broken`，发告警，并拒绝使用。**绝不静默继续。**

**模型可以帮忙写草稿（比如建议中文含义），但只能是草稿，必须人工批准。**

### 2.3 指标查询和编译

模型只输出结构，不写 SQL：

```json
{
  "metric": "revenue/v1",
  "dimensions": ["month"],
  "filters": [{"dimension": "region", "op": "=", "value": "华东"}],
  "periods": [{"start": "2025-07-01", "end": "2025-08-31"}],
  "order": "month",
  "limit": 100
}
```

**编译器（`data/metric_compiler.py`，确定性）：**

```text
1 校验：指标存在；维度和筛选都在定义内；值用参数化或枚举校验
2 选表和 Join：只用语义层登记的路径
3 生成 sqlglot AST（不拼字符串）
4 加必选筛选（模型不能去掉）和时间范围
5 输出 SQL + 自动生成的 query_contract
```

**注入防护：** 筛选值先和枚举或语义层比对，再以字面量写入 AST；`validate_sql` 仍会再检查一遍。

**现有验证流程怎么复用：** 编译结果是普通 `SQLCandidate`，后面的 `assess_metric_query`、工具流水线、结果评估全部不变。

### 2.4 两条路径的选择

| 情况 | 路径 |
|---|---|
| 规划命中指标，模型能填 `MetricQuery`，编译成功 | 指标路径，跳过 SQL 语义复核 |
| 编译失败（维度不支持等） | 退回模型 SQL 路径，并记录原因 |
| 没命中指标（明细、探索类） | 模型 SQL 路径（现有） |

**跳过 SQL 语义复核要批准。** 省一次调用，但语义复核是一道检查；影子阶段先比较两者一致性。

---

## 3. 一次查询的具体过程

“比较华东区 2025 年 7 月与 8 月已交付订单销售额”：

```text
规划      metric_refs=["revenue/v1"], periods=[7月, 8月], entity=华东
生成      模型输出 MetricQuery（约 100 token，比写 SQL 少）
编译      SELECT date_trunc('month', o.order_date) AS 月份,
                 ROUND(SUM(o.total_amount), 2) AS 销售额
          FROM sales_orders o JOIN customers c ON …
          WHERE o.status = 'delivered'             ← 必选筛选，不靠模型
            AND c.region_code = 'EAST'             ← 枚举映射
            AND o.order_date >= … AND o.order_date < …
          GROUP BY 1 ORDER BY 1 LIMIT 100
校验      validate_sql 通过
执行      公司数据源、只读、10 秒超时
评估      assess_metric_query=supported，结果 2 行
证据      记录 metric_ref、semantic_model_version、source="compiled"
```

---

## 4. 其他修复

### 4.1 `template_query`（B3）

**建议下线。** 目前主链没有调用（只在 `TemplateQueryTool` 和白名单中出现），而且它用平台默认凭据连库（`sql_executor.py:60-69`），与“每公司一个数据源”冲突。

```text
1 默认白名单去掉 template_query（新任务）
2 删除 template_query.py、query_registry.py、execute_registered_readonly_query
3 旧快照里的名字由注册表拒绝（tool_not_registered）
```

指标编译器已经覆盖了“登记查询”的目的。

### 4.2 概念比较

`_contract_gaps` 用字符串比较（`data_agent.py:388`）。改成先按语义层的别名归一，**归一后再比较**；不能归一的词仍按原文比较。这样“营收”和“销售额”不再误判，同时不放宽未知词。

### 4.3 过度拦截（B4）

先逐题定位那 4 道被拦的 SQL，归类原因（如合法的日期函数、CTE 写法）。**放宽校验规则要批准，并且对抗集要全部继续拦截。** 每放宽一条，就增加一组对抗用例。

### 4.4 可修复的执行错误

日期格式等错误现在不重试【记录】。把这类错误映射为 `caller_error` 并返回**脱敏**的错误类型（不把数据库原始报错给模型），修复一次。

### 4.5 查询成本保护

| 控制 | 做法 |
|---|---|
| 事前 | 执行前 `EXPLAIN (FORMAT JSON)`，估算成本超阈值就拒绝并提示缩小范围 |
| 事中 | `statement_timeout` 已有；每数据源并发上限（Redis 信号量，防止占满客户的库） |
| 事后 | 行数上限（现有 1000）；结果 token 上限（工具平台） |

**EXPLAIN 的估算可能不准，** 先影子记录，有数据后再启用拒绝。

### 4.6 事实生成

`rows[:5]` 改成按结果类型处理：聚合结果全部保留；多行结果生成“前 N 行 + 总行数 + 合计”，并写明“共 N 行，仅列出前 M 行”。`Limitation` 里也要注明。

---

## 5. 失败路径

| 场景 | 系统行为 | 用户看到 |
|---|---|---|
| 语义层未配置 | 走模型 SQL 路径 | 无感知；准确率可能较低 |
| 指标被标记 `broken` | 不使用该指标，写告警；是否退回模型路径看配置，默认不退回（口径可能已变） | 明确说明指标暂不可用 |
| 编译失败 | 退回模型路径，记录原因 | 无感知 |
| 代码生成的 SQL 没过校验 | **视为缺陷**，告警，任务失败，不退回 | 明确失败 |
| 空结果 | `no_matching_records`（现有） | 说明无匹配记录 |
| 经营库超时 | 有限重试、熔断（工具平台） | 明确失败 |
| 并发达到上限 | 排队短暂等待后失败 | 提示稍后重试 |

---

## 6. 配置

| 配置项 | 默认值 |
|---|---|
| `DATA_METRIC_PATH_MODE` | `off`（`off` / `shadow` / `enforce`） |
| `DATA_SKIP_SQL_REVIEW_FOR_COMPILED` | `false` |
| `DATA_BROKEN_METRIC_FALLBACK` | `false` |
| `DATA_QUERY_COST_GUARD` | `shadow` |
| `DATA_QUERY_COST_LIMIT` | 用基线确定 |
| `DATA_SOURCE_MAX_CONCURRENCY` | 3 |
| `SQL_MAX_ROWS` | 1000（现有默认） |

---

## 7. 落地步骤

**验证命令是计划，尚未运行。** 改表和 SQL 校验都要批准。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B3 下线模板查询** | 见 4.1 | 工具注册表测试；全量测试 | revert |
| **B4a 语义层表和种子** | 迁移、`catalog/semantic_store.py`；演示定义转种子 | 加载结果和硬编码**逐字段相同**；回放不变 | 继续读硬编码 |
| **B4b 读取切换** | `metric_catalog`、`schema_selection`、`facts`、`sql_generation` 改读语义层 | 提示词哈希不变；SQL 评测不变；**新增“第二家公司”测试不依赖演示定义** | 开关 |
| **B4c 管理 API** | 草稿、校验、批准；表结构变化比对 | 未批准不可用；跨公司 0 | 默认无 API |
| **B4d 指标编译器** | `metric_compiler.py`；表驱动测试 | 所有演示指标编译后都通过校验，结果和标准答案相同 | 不接入 |
| **B4e 影子比对** | 主路径不变，同时编译并比较 SQL 结果 | 差异报告 | 关闭 |
| **B4f 指标路径启用**（**需批准**） | `enforce`；费用要评估 | SQL 连续 3 轮不低于 22/24；放行错误数字 0；费用下降 | `off` |
| **B4g 其他修复** | 4.2～4.6 各一个工单 | 各自测试；对抗集全过 | 单独回退 |

---

## 8. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 新建测试公司，配置不同表结构 | 不依赖任何演示硬编码就能回答 |
| 问“销售额”但模型试图不加已交付筛选 | SQL 里仍有必选筛选 |
| 筛选值写注入内容 | 不在枚举就拒绝；校验再拦一次 |
| 表结构字段改名后重新发现 | 指标 `broken`，告警，不静默运行 |
| 改语义层时有进行中的任务 | 该任务用旧版本 |
| SQL 评测和对抗集 | 准确率不降；攻击全拦 |

**仍需开工时确认：** `metric_validation.py` 如何判定指标（编译结果要能通过）；`sqlglot` 生成 PostgreSQL 的细节；真实客户的表结构可能复杂得多，语义层 schema 要留版本；SQL 语义复核是否能在所有指标路径跳过要看比对数据。
