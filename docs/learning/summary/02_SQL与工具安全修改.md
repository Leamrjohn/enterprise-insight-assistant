# 02 SQL 与工具安全修改

**这部分回答的问题：** SQL 是模型写的，模型可能写错，也可能被问题里夹带的内容诱导。怎样保证它不会造成破坏？

**核心思路：纵深防御。** 设置多层防护，每一层都要能单独挡住攻击。不靠提示词约束模型，因为提示词只是建议，只有代码和数据库权限是强制的。

```text
第 1 层 契约    只允许单条 SELECT
第 2 层 AST     检查 SQL 的语法树（把 SQL 解析成树形结构）        ← 4.3 加固
第 3 层 范围    限定当前公司的数据（公司快照）
第 4 层 执行    只读账号、只读事务、超时、行数上限                 ← 4.4 测试、4.4.1 补漏
第 5 层 审计    记录工具调用
```

---

## 1. AST 层加固（4.3）

**为什么改：** 我用 54 种攻击测试，有 27 种能通过 AST 检查。

**典型例子：**

```sql
WITH d AS (DELETE FROM customers RETURNING 1) SELECT * FROM d
```

最外层确实是 `SELECT`，所以通过了，但它里面藏着 `DELETE`。

| | 修改前 | 修改后 |
|---|---|---|
| 写入语句 | 只看最外层 | 遍历整棵语法树 |
| `FOR UPDATE` 等行锁 | 可以通过 | 拒绝 |
| `pg_sleep`、`pg_read_file`、`set_config` 等危险函数 | 可以通过 | 拒绝 |
| 54 种攻击 | 拦截 27 种 | 全部拦截 |
| 45 条模型历史真实 SQL | 不适用 | 全部仍可通过（防误拦） |

```python
for node in statement.walk():            # 遍历整棵树
    if isinstance(node, _WRITE_NODES):   # DELETE、UPDATE 等
        raise ValueError("查询中不允许包含写入或结构修改语句")
    if isinstance(node, exp.Lock):
        raise ValueError("查询中不允许加锁")
```

代码见 [sql_validator.py](../../../backend/app/modules/analysis/data/sql_validator.py)。

**当时为什么没出事：** 这些攻击虽然过了 AST，但被执行层的只读账号拦住了。这正是纵深防御的作用。

**为什么执行层能拦还要改 AST：** 数据库权限可能被配错。AST 规则写在代码里，可以测试、可以审查，是独立的一道防线。

**一个坑：** 第一次探测用了不存在的表 `orders`，所有攻击都被“表不存在”拦下，看起来非常安全，其实什么都没测到。换成真实表名后才发现 27 种能通过。

**取舍：** 危险函数用的是黑名单（决策 D20）。白名单更严，但模型合理使用新函数时会被误拦，需要先有更多样本。

**测试：** [test_sql_adversarial.py](../../../backend/tests/unit/analysis/test_sql_adversarial.py)

---

## 2. 工具拒绝说明（4.2）

**为什么改：** 以后要让模型自己选工具（4.5）。模型被拒绝后，只有知道原因才能改正。

| 情况 | 修改前 | 修改后 |
|---|---|---|
| 调用次数用完 | 工具调用不在已授权范围内。 | 本任务的工具调用次数已用完，请基于已有结果作答…… |
| 查了别的公司 | 工具调用不在已授权范围内。 | 只能查询当前任务所属公司的数据。 |

一共 10 种错误码有专门说明，未知错误码回落到原来的通用句。代码见 [tool_runtime.py](../../../backend/app/modules/runtime/tool_runtime.py)。

**我撤回的一个修改：** 我本来想让工具直接拒绝多余参数，但有 3 个已有测试明确规定“丢弃多余参数后继续”。两种做法同样安全，所以保留原设计（决策 D21），不为我的偏好改测试期望。

---

## 3. 执行层对抗测试（4.4）

**为什么做：** 既然 AST 曾漏掉一半攻击，就要证明执行层真的挡得住。之前只人工查过一次，没有自动测试，以后被改坏也不会有人发现。

**做法的关键：** 测试时把 AST 校验替换成空函数，让攻击直接到达真实数据库。否则攻击先被 AST 拦下，执行层等于没被测。

| 攻击 | 被谁拦住 |
|---|---|
| CTE 内写入、`FOR UPDATE`、`SELECT INTO` | 只读事务或账号权限 |
| 读服务器文件、导入大对象 | 账号权限 |
| `dblink`（连接其他数据库） | 函数不存在 |
| `pg_sleep(3)` | 300 毫秒超时 |
| 在语句内用 `set_config` 取消超时 | 无效，仍被取消 |
| 显式开读写事务后 `INSERT`、建表、改角色 | 账号权限 |
| 用 acme 的账号连 beta 的数据库 | 连接失败 |

**安全措施：** 写入尝试都不提交，不会改动经营数据。

代码见 [test_sql_execution_layer.py](../../../backend/tests/integration/analysis/test_sql_execution_layer.py)，一共 26 项，加上下一节的 3 项共 29 项。

**局限：** 需要设置环境变量才会运行，否则整个模块跳过。

---

## 4. 模板查询加只读事务（4.4.1）

**先说明我的错误：** 我最初报告这条路径“用超级用户连接”，这是错的。我查的是自己排查时登录用的账号，不是程序实际用的账号。从真实路径查询后才确认：实际账号 `business_readonly` 不是超级用户，22 张表都没有写权限。真实的缺口只有“没开只读事务”，风险比我说的小。

| | 修改前 | 修改后 |
|---|---|---|
| `transaction_read_only` | `off` | `on` |
| 写入被谁拦 | 只有账号权限 | 只读事务先拦，账号权限是第二层 |

```python
conn = psycopg.connect(..., options="-c default_transaction_read_only=on")
cur.execute("SET TRANSACTION READ ONLY")
```

**测试为什么断言具体错误类型：** 修改前账号权限也会报错。如果只检查“有报错”，修改前测试也能通过。指定 `ReadOnlySqlTransaction`，才能证明是只读事务这一层起了作用。

**意义：** 只改两行，代价很小。账号权限万一被配错，还有一层防护。

---

## 这部分怎么验证

AST 对抗测试（不需要数据库）：

```bash
cd backend && ../.venv/Scripts/python -m pytest tests/unit/analysis/test_sql_adversarial.py -q
```

执行层测试需要先启动项目容器，并设置环境变量 `ACME_DEMO_DATABASE_PASSWORD`（键名写在 `docker-compose.yml` 里）：

```bash
cd backend && ../.venv/Scripts/python -m pytest tests/integration/analysis/test_sql_execution_layer.py -q
```

如果输出显示全部 skipped，说明环境变量没设置，**这不代表通过**。

相关决策：D20～D23。调查报告：[stage4_tool_sql_survey.md](../../design/stage4_tool_sql_survey.md)。
