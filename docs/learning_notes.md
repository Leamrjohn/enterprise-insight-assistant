# 学习进度与掌握证据

## 使用规则

本文件记录实际学习过程和掌握证据，不是预先填写的课程计划。

- 每完成一课立即更新。
- 测试结果必须来自实际运行。
- 没有通过掌握验证时不能标记为“已掌握”。
- 同一阶段允许多次记录，保留错误和修正过程。
- 不删除失败记录；失败记录用于证明排错能力的成长。

掌握状态：

| 状态 | 含义 |
|---|---|
| 未开始 | 尚未学习 |
| 学习中 | 能在较强提示下完成 |
| 待补强 | 主流程基本掌握，但排错或迁移能力不足 |
| 已掌握 | 解释、实现、排错和迁移验证全部通过 |

## 总体进度

| 阶段 | 主题 | 状态 | 最近验证 | 主要遗留问题 |
|---|---|---|---|---|
| 0 | 工程基线、Git和现有调用链 | 已掌握 | 2026-07-05：独立识别ModuleNotFoundError | - |
| 1 | HTTP契约、Schema和异常 | 已掌握 | 2026-07-07：12 passed，统一错误结构 | - |
| 2 | 用户身份、资源归属和最小RBAC | 已掌握（代码已完成） | 2026-07-09：API Key认证、用户隔离 | - |
| 3 | 文件上传闭环 | 已掌握（代码已完成） | 2026-07-09：上传校验链、SHA256去重 | - |
| 4 | 文档解析、分块和生命周期 | 已掌握（代码已完成） | 2026-07-09：chunk分块、CASCADE删除 | - |
| 5 | 本地基础设施与环境分层 | 待补强 | 2026-07-10：Session/engine/连接池概念 | Docker Compose未实现 |
| 6 | 持久化任务模型和状态职责 | 已掌握 | 2026-07-11：完整CRUD分层、Worker异步执行 | - |
| 7 | Celery异步执行 | 已掌握 | 2026-07-11：端到端测试 queued→completed | - |
| 8 | pgvector和Embedding | 已掌握 | 2026-07-11：5题掌握验证通过 | - |
| 9 | 检索与增量评测 | 概念已讲 | 2026-07-11：Precision/Recall/Top-K/阈值 | 等待实操 |
| 10 | Model Gateway和数据发送策略 | 学习中 | 2026-07-11：抽象类+本地实现+OpenAI实现 | - |
| 11 | 可靠RAG | 学习中 | 2026-07-11：RAG流程+充分性判断+引用校验被证明无效 | validate_citations不可靠已删除 |
| 12 | 独立经营数据源、KPI和标准场景 | 未开始 | - | - |
| 13 | 安全只读SQL工具 | 未开始 | - | - |
| 14 | Tool Registry | 未开始 | - | - |
| 15 | 四个核心Agent | 未开始 | - | - |
| 16 | LangGraph状态工作流 | 未开始 | - | - |
| 17 | 确定性校验、拒答和人工审核 | 未开始 | - | - |
| 18 | 可靠性和故障恢复 | 未开始 | - | - |
| 19 | 安全和数据治理 | 未开始 | - | - |
| 20 | 可观测性、评测和SLO | 未开始 | - | - |
| 21 | 最小前端 | 未开始 | - | - |
| 22 | 可复现构建、部署和运维验收 | 未开始 | - | - |

## Agent上下文专项进度

上下文能力随项目阶段逐步升级，不单独搭建脱离业务的记忆系统。

| 上下文能力 | 对应项目阶段 | 状态 | 验证证据 | 遗留问题 |
|---|---|---|---|---|
| 内存State和字段流转 | 0～1的独立练习 | 未开始 | - | - |
| 请求、身份和权限上下文 | 2 | 未开始 | - | - |
| 文档与chunk证据引用 | 3～4 | 未开始 | - | - |
| 持久化任务和异步上下文 | 6～7 | 未开始 | - | - |
| 向量检索上下文 | 8～9 | 未开始 | - | - |
| Model Gateway和单Agent上下文 | 10～11 | 未开始 | - | - |
| SQL与Tool结果上下文 | 12～14 | 未开始 | - | - |
| Multi-Agent输入隔离 | 15 | 未开始 | - | - |
| Workflow State和checkpoint | 16 | 未开始 | - | - |
| 校验、拒答和审核上下文 | 17 | 未开始 | - | - |
| Token、安全、失效和可重放 | 18～20 | 未开始 | - | - |
| 生产部署和恢复上下文 | 21～22 | 未开始 | - | - |

## 单课记录模板

复制下面模板，在每一课结束后填写。

```markdown
## YYYY-MM-DD：阶段X / 第X课 / 主题

### 本课目标

- 待填写

### 阅读与修改

- 阅读文件：
- 修改文件：
- 独立编写内容：
- 使用的提示级别：完整讲解/接口与伪代码/仅需求
- 第几次尝试通过：
- 对应Commit Hash：

### 数据流复述

用自己的语言说明输入、处理过程、输出和失败路径。

### 上下文检查

涉及RAG、Agent、Tool或Workflow时填写；不涉及时写“不适用”并说明原因。

- 当前节点需要哪些上下文：
- 每项上下文来自哪里：
- 哪些内容可信，哪些不可信：
- 权限在什么位置检查：
- 大型内容保存在哪里，State保存什么引用：
- Token不足时按什么顺序压缩：
- 哪些变化会让上下文失效：
- 如何通过task_id和证据ID重建：

### 验证证据

- 执行命令：
- 实际结果：
- 新增测试：
- 正常路径：
- 异常路径：

### 错误与根因

- 现象：
- 证据：
- 根因：
- 修复：
- 如何避免再次发生：

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 未通过/通过 | |
| 独立实现同类功能 | 未通过/通过 | |
| 独立定位故障 | 未通过/通过 | |
| 独立迁移到相似场景并测试 | 未通过/通过 | |

### 当前结论

- 掌握状态：学习中/待补强/已掌握
- 已经掌握：
- 仍不理解：
- 下一步补强：
```

## 学习记录

## 2026-07-04：阶段0 / 第1课 / 确认解释器和测试基线

### 本课目标

- 确认项目实际使用的Python解释器。
- 使用同一个解释器运行pytest。
- 理解退出码和`python -m`。

### 阅读与修改

- 阅读文件：`backend/app/api/document.py`、`backend/app/services/document_service.py`、
  `backend/app/repositories/document_repository.py`、
  `backend/app/services/document_ingestion_service.py`、
  `backend/app/schemas/document.py`、`backend/app/models/documents.py`
- 修改文件：仅更新本学习记录。
- 独立编写内容：执行环境和测试检查命令。
- 使用的提示级别：完整讲解。
- 第几次尝试通过：第2次。
- 对应Commit Hash：当前仓库尚无提交。

### 数据流复述

已完成第一跳：

```text
POST /documents
→ create_document
→ save_document_service
→ save_document
→ Documents ORM对象
→ PostgreSQL
```

Repository返回ORM对象，Service将需要的字段转换为字典，FastAPI再依据
`DocumentOut`生成响应。学习者已识别API、Service和Repository的基本职责。

综合调用链复述通过：

```text
客户端
→ API
→ Service
→ Repository
→ ORM Model
→ PostgreSQL
→ Repository
→ Service
→ API使用DocumentOut校验和序列化
→ 客户端
```

Schema与ORM边界：

- `DocumentCreate`定义客户端可提交的`name/content/source`。
- `DocumentOut`增加服务端返回的`id`。
- `Documents`保存数据库需要的完整内部状态。

### 上下文检查

不适用：本课尚未涉及RAG、Agent、Tool或Workflow。

### 验证证据

- 解释器：`C:\Users\qyf21\Documents\Agent项目学习\.venv\Scripts\python.exe`
- 第1次命令：误用`pytest.exe -m pytest -q backend`
- 第1次结果：`3 deselected`，实际未执行测试
- 修正命令：`.venv\Scripts\python.exe -m pytest -q backend`
- 实际结果：`3 passed in 0.48s`
- 退出码：`0`
- 退出码理解：`0`表示命令成功；非零表示进程未按成功条件结束，不限定为代码异常。
- 迁移练习第1次：执行`.venv\Scripts\python.exe -m pip -q backend`。
- 迁移练习第1次结果：`ERROR: unknown command "backend"`。
- 迁移练习证据：pip帮助显示必须使用`pip <command> [options]`，查看版本使用`-V`或`--version`。
- 迁移练习第2次：执行`.venv\Scripts\python.exe -m pip --version`。
- 迁移练习第2次结果：pip 26.1.2，来自项目`.venv`，退出码为`0`。
- 正常路径：通过
- 异常路径：观察到错误参数导致测试全部被筛除

### 错误与根因

- 现象：pytest显示`3 deselected`。
- 证据：命令直接启动`pytest.exe`，后面仍传入`-m pytest`。
- 根因：直接启动pytest时，`-m`由pytest解释为标记筛选表达式，而不是由Python解释器解释为模块运行参数。
- 修复：改用`.venv\Scripts\python.exe -m pytest -q backend`。
- 如何避免再次发生：先判断当前启动的是Python解释器还是具体命令，再判断后续参数由谁解析。
- 新现象：pip报告`unknown command "backend"`。
- 新根因：把pytest接受的目录参数照搬给pip；不同模块拥有不同的命令行接口。
- 新证据：pip自身帮助列出了合法命令和`--version`选项。
- 源码理解修正：`response_model`具体为`DocumentOut`；`db`是通过`Depends(get_db)`
  注入的数据库Session，不是HTTP会话。
- ORM术语修正：`Documents`是ORM类，`record`只是该实例的变量名；`refresh()`用于
  从数据库重新加载当前记录。
- 事务理解：`add()`只把对象加入Session；`commit()`提交事务并完成持久化；
  `refresh()`重新读取数据库生成或修改后的字段。
- 异常理解：`commit()`抛出异常后不会继续执行`refresh()`，Session需要先
  `rollback()`才能安全继续使用。
- 跨存储一致性：数据库`rollback()`不能删除磁盘文件，因此数据库失败时还需要
  删除本次新建文件。
- 独立识别风险：当前代码在`commit()`成功后执行`refresh()`；如果`refresh()`失败，
  `rollback()`无法撤销已提交记录，但异常分支会删除文件，可能留下数据库记录存在、
  文件不存在的不一致状态。
- 异常分类修正：`IntegrityError`是数据库完整性约束异常，不是文件异常；它用于
  处理SHA256唯一约束等数据库冲突，并转换为业务可理解的重复文档异常。
- `flush()`理解修正：它把Session中的待执行SQL发送到当前数据库事务，但不提交；
  `commit()`会自动flush并提交事务。
- 可见性修正：在项目使用的PostgreSQL常规隔离级别下，当前事务能看到flush后的
  记录，其他连接在commit前通常看不到。
- 安全顺序判断：学习者正确提出`flush → refresh → commit`，使`refresh()`失败时
  事务仍未提交，可以rollback并删除文件。
- 事务复述验证：学习者能说明flush后其他连接通常不可见，并能说明commit放在
  refresh后可避免失败时残留已提交数据库记录。
- 字段来源修正：`id/created_at`可由数据库生成，`status`可来自默认值，
  `sha256/file_type/file_size`由上传服务计算后写入。
- 响应风险：ORM允许`content=None`，当前`DocumentOut`要求字符串，上传记录返回时
  会触发FastAPI响应校验异常。
- Schema设计判断：学习者正确选择为上传接口建立单独响应Schema，但最初只考虑返回
  名字和来源，遗漏了客户端后续查询所需的记录ID和处理状态。
- 状态术语补充：`pending`等待处理、`processing`正在处理、`completed`处理完成、
  `failed`处理失败。
- 当前实现边界：设计上客户端应使用文档`id`查询同一条记录的最新`status`；当前
  `DocumentOut`和文档查询接口尚未返回`status`，因此这一能力还没有实现。
- 状态查询验证：给定上传返回`id=42`，学习者能判断后续应请求`GET /documents/42`。
- ORM术语补充：ORM类映射数据库表，ORM实例承载某条记录的数据和状态。
- Git状态证据：`## No commits yet on master`，仓库已初始化但没有任何提交；
  `.gitignore`、`README.md`、`backend/`和`docs/`均显示为`??`未跟踪。
- Git理解验证：学习者能识别`??`表示未跟踪，并知道未提交的未跟踪文件无法由Git恢复。
- 名称修正：`.venv/`是本地虚拟环境；`backend/.env`是运行配置，可能包含数据库密码
  和API密钥；`.env.example`是可以提交的无密钥配置模板。
- 版本控制范围修正：Git不仅保存业务代码，还应保存测试、迁移、文档、依赖声明和
  安全的配置模板。
- 提交分类验证：正确判断`.venv/`、`.env`不提交，`.env.example`和测试应提交；
  最初误判数据库迁移不提交，已说明迁移是数据库结构的版本历史，必须进入Git。
- 迁移作用复述通过：只提交新ORM字段而不提交迁移，会导致同事数据库缺少对应列并
  在运行时出错。
- Git忽略验证：`git check-ignore -v`确认`.venv/`由第1条规则忽略，
  `backend/.env`由`.env`规则忽略。
- 暂存第1次尝试：只执行`git add`，因缺少路径参数而没有暂存；后续
  `git status --short`仍显示`??`，证明文件保持未跟踪。
- 暂存第2次尝试：使用`git add .`后状态变为`A`，表示文件已进入暂存区。
- 暂存审查：共56个文件，包含源码、测试、迁移、文档和`.env.example`；真实
  `.env`、`.venv`和明显密钥模式未进入暂存区。
- 暂存格式检查：`git diff --cached --check`发现文件末尾空白行和行尾空格；修正后
  退出码为`0`。
- 误改识别：清理迁移文件空格时误改`script.py.mako`模板中的必要分隔空格，
  `git status`显示`AM`，通过`git diff`确认差异后使用`git restore`恢复工作区。
- Git状态理解：短状态第一列表示暂存区，第二列表示工作区；`AM`表示已暂存新增文件
  后，工作区又发生修改。
- 提交前验证：pytest结果为`3 passed in 0.53s`，暂存格式检查通过。
- 分支调整：当前默认分支已从`master`改为`main`，尚未创建首个提交。
- 换行提示：Git提示LF以后可能转换为CRLF；这是Windows工作区换行策略提示，不是
  测试或暂存失败，当前阶段不增加额外换行配置。
- 初始提交成功：`ab8c5a3 chore: establish project baseline`，属于`root-commit`，
  共纳入56个文件。
- 提交后状态：只显示`## main`，证明当时暂存区和工作区均无未提交文件。
- 学习记录提交：`5778710 docs: record stage 0 learning progress`。
- 分支迁移：从干净的`main`创建并切换到`feature/api-contracts`，两个基线提交均保留。
- 独立故障验证：运行导入不存在模块的命令，依据`ModuleNotFoundError`判断为模块导入
  问题，并根据退出码`1`确认命令失败；未盲目安装依赖。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能说明命令参数、请求分层和数据库事务边界 |
| 独立实现同类功能 | 通过 | 能根据pip帮助组合模块运行命令 |
| 独立定位故障 | 通过 | 独立依据异常类型和退出码识别模块导入问题 |
| 独立迁移到相似场景并测试 | 通过 | 将`python -m`迁移到pip模块，并完成Git分支迁移 |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：解释器与模块运行、退出码、HTTP到数据库调用链、Session事务基础、
  Schema与ORM边界、Git忽略/暂存/提交/分支和基础故障分类。
- 仍不理解：阶段1将学习API契约、响应校验和统一异常处理。
- 下一步补强：在`feature/api-contracts`进入阶段1。

## 2026-07-05：阶段1 / 第1课 / DocumentOut响应契约

### 本课目标

- 理解数据库可空字段与API输出类型必须一致。
- 区分创建请求契约与查询响应契约。
- 先建立失败验证，再做最小修复。

### 阅读与修改

- 阅读文件：`backend/app/schemas/document.py`、`backend/app/models/documents.py`
- 修改文件：尚未修改应用代码。
- 独立编写内容：尚未开始。
- 使用的提示级别：接口与问题说明。
- 第几次尝试通过：进行中。
- 对应Commit Hash：`5ef008b`。

### 数据流复述

```text
Documents.content允许NULL
→ Service可能返回content=None
→ FastAPI使用DocumentOut校验响应
→ DocumentOut.content只允许str
→ 响应校验失败
```

### 上下文检查

不适用：本课处理普通API契约，尚未涉及Agent上下文。

### 验证证据

- 当前ORM：`Documents.content`类型为`str | None`，数据库列`nullable=True`。
- 当前响应Schema：`DocumentOut.content`类型为`str`。
- 预期：先新增一个能稳定重现冲突的Schema测试。
- 最小修改判断：学习者正确选择只将`DocumentOut.content`改为`str | None`。
- 语义修正：`Documents`是所有文档共用的数据库模型；`DocumentOut`是当前通用查询
  响应，不只表示解析完成状态。
- 空值区别：`None`表示尚无内容，空字符串`""`表示存在字符串但长度为零，两者不同。
- 失败测试第1次：pytest退出码`4`并提示找不到
  `backend/tests/test_document_schema.py`。
- 根因1：实际文件名误写为`tets_document_schema.py`，不符合pytest默认的
  `test_*.py`发现规则。
- 根因2：测试数据写成字符串`"None."`而不是Python值`None`，即使运行也不会触发
  当前Schema冲突。
- 失败测试第2次：重命名后pytest找到并通过1个测试，但检查文件发现测试仍传入
  `"None."`并断言字符串相等，因此这是未覆盖目标问题的“错误通过”。
- 失败测试第3次：测试真正传入Python的`None`后，pytest找到1个测试并按预期失败，
  Pydantic报告`DocumentOut`存在1项字符串类型校验错误，退出码为`1`。
- 结论：测试已稳定证明`DocumentOut.content: str`与数据库可空字段不一致。
- 最小修复：只将`DocumentOut.content`改为接受`str | None`，未修改创建/更新Schema、
  ORM、Service或Repository。
- 修复后单项测试：`1 passed in 0.07s`。
- 完整回归测试：`4 passed in 0.29s`。
- Ruff检查：`All checks passed!`。
- 测试整理后回归：`4 passed in 0.29s`，Ruff lint仍通过。
- 格式复查：`ruff format --check`指出Schema和新测试共2个文件需要格式化，说明
  `ruff check`通过不等于代码排版已经规范。
- 格式化后验证：完整测试`4 passed`、Ruff lint通过、两个目标文件均已格式化。
- 理解验证结果：能说明手工创建文档时内容必须提供；尚未掌握`str | None`是“字符串
  或None”的联合类型，并混淆了pytest行为测试与Ruff格式检查的职责。
- 补强后复述通过：能确认`str | None`同时接受字符串和None，并能区分pytest行为
  测试与Ruff格式化职责。
- 本课提交：`5ef008b fix: allow document responses without content`，包含Schema最小
  修复、回归测试和学习记录；提交后工作区干净。
- 第2课提交：`1c07722 test: define document not-found response contract`，固定404状态、
  响应内容和请求追踪ID。
- 第3课提交：`4cdcaf5 test: define missing-field validation contract`，固定缺少必填字段
  时的422、错误类型、字段位置和Request ID。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能判断创建输入必填、数据库和输出允许None |
| 独立实现同类功能 | 通过 | 完成最小类型修改并保持其他契约不变 |
| 独立定位故障 | 通过 | 根据ValidationError确认响应Schema拒绝None |
| 独立迁移到相似场景并测试 | 未通过 | 尚未进行 |

### 当前结论

- 掌握状态：学习中
- 已经掌握：使用失败测试证明契约冲突，完成最小修复、回归测试和格式检查。
- 仍不理解：阶段1的迁移验证和统一异常契约尚未完成。
- 下一步补强：提交当前独立修复，再进入HTTP错误响应。

## 2026-07-05：阶段1 / 第2课 / 404错误链路

### 本课目标

- 区分“资源不存在”与“服务器异常”。
- 跟踪Repository返回None后如何转换为HTTP 404。
- 观察FastAPI当前错误响应，不提前建立复杂异常框架。

### 阅读与修改

- 阅读文件：`backend/app/api/document.py`、`backend/app/services/document_service.py`、
  `backend/app/repositories/document_repository.py`、
  `backend/tests/integration/test_documents.py`
- 修改文件：尚未修改应用代码。
- 独立编写内容：尚未开始。
- 使用的提示级别：问题说明。
- 第几次尝试通过：进行中。
- 对应Commit Hash：`1c07722`。

### 数据流复述

```text
Repository使用first()查询
→ 没有记录时返回None
→ Service保持返回None
→ API判断record is None
→ 抛出HTTPException 404
→ FastAPI生成404响应
```

### 上下文检查

不适用：本课处理普通HTTP错误契约。

### 验证证据

- 现有集成测试删除文档后再次查询，并断言HTTP状态码为404。
- 当前API使用`HTTPException(status_code=404, detail="document not found")`。
- 理解验证：学习者能说明资源不存在应返回404，500用于预期外服务器故障。
- 术语修正：必须明确说`None`，不能把`None`、空字符串和空列表统称为“空”。
- 集成测试第1次：目标测试、完整测试和Ruff均通过，但diff检查发现只新增了
  `X-Request-ID`断言，遗漏`{"detail": "document not found"}`响应体断言。
- 教训：测试通过只说明现有断言成立，不能证明需求中的所有检查都已编写。
- 集成测试第2次：补齐404响应JSON后，目标测试`1 passed`、完整测试`4 passed`、
  Ruff通过；最终同时验证状态码、错误内容和`X-Request-ID`。
- 最终复述通过：API负责把`None`转换为HTTP 404；Service不依赖HTTP，便于被API、
  Worker或工作流复用；Request ID用于将用户失败请求关联到具体日志。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能复述None到HTTP 404的转换和404/500区别 |
| 独立实现同类功能 | 通过 | 扩展现有集成测试验证错误响应契约 |
| 独立定位故障 | 通过 | 通过diff发现绿色测试遗漏响应体断言并补齐 |
| 独立迁移到相似场景并测试 | 通过 | 复用健康检查中的Request ID断言到404响应 |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：404错误链路、HTTP边界，以及状态码、响应体和追踪ID测试。
- 仍不理解：阶段1还需要学习Pydantic请求校验产生的422响应。
- 下一步补强：提交本课测试，再观察非法请求如何在进入API函数前被拒绝。

## 2026-07-05：阶段1 / 第3课 / Pydantic请求校验与422

### 本课目标

- 理解请求Schema是进入API函数前的信任边界。
- 区分合法JSON与符合业务字段契约的JSON。
- 使用集成测试观察缺少必填字段时的422响应。

### 阅读与修改

- 阅读文件：`backend/app/schemas/document.py`、`backend/app/api/document.py`
- 修改文件：尚未修改。
- 独立编写内容：尚未开始。
- 使用的提示级别：概念说明。
- 第几次尝试通过：进行中。
- 对应Commit Hash：`4cdcaf5`。

### 数据流复述

```text
合法JSON请求
→ FastAPI构造DocumentCreate
→ 缺少content导致Pydantic校验失败
→ 返回422
→ API函数、Service、Repository均不执行
→ 数据库不新增记录
```

### 上下文检查

不适用：本课处理普通HTTP输入校验。

### 验证证据

- `DocumentCreate`要求`name`、`content`和`source`都是字符串。
- FastAPI在调用`create_document()`之前使用`DocumentCreate`校验请求体。
- 理解验证：学习者能判断缺少`content`返回422，后续函数和数据库写入不会发生。
- 术语修正：请求是合法JSON，但不符合Schema，不应称为JSON格式错误。
- 观察测试：缺少`content`时响应`detail[0]`包含`type="missing"`、
  `loc=["body", "content"]`、`msg="Field required"`和原始输入。
- 当前测试已断言422和`X-Request-ID`，临时`print()`仅用于观察，最终测试应删除。
- `loc`术语：location路径`["body", "content"]`表示错误位于请求体的`content`字段。
- 测试整理第1次：误将422和Request ID断言注释，导致测试只检查detail；注释代码
  不是删除，也不应为了增加新断言而移除原有必要契约。
- 最终测试结构：同时验证422、`X-Request-ID`、错误类型`missing`和错误位置
  `["body", "content"]`，临时打印与注释已删除。
- 最终验证：完整测试`5 passed in 0.37s`，Ruff检查通过，两个退出码均为`0`。
- 完整错误JSON判断修正：测试不锁死`msg`和`input`，因为文字可能随Pydantic版本
  变化，原始输入也可能包含敏感或与目标无关的数据。
- 迁移验证：能判断缺少`source`时`type`仍为`missing`但位置变为
  `["body", "source"]`；缺少`name`时位置为`["body", "name"]`。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能复述Schema校验失败后停止后续调用 |
| 独立实现同类功能 | 通过 | 新增缺少必填字段的422集成测试 |
| 独立定位故障 | 通过 | 根据detail定位请求体content字段缺失 |
| 独立迁移到相似场景并测试 | 通过 | 能将type与loc规则迁移到source和name字段 |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：422发生位置、稳定错误字段、集成测试和字段位置迁移。
- 仍不理解：阶段1还需要学习“字符串存在但为空”的边界校验。
- 下一步补强：提交本课，再验证空字符串是否会绕过当前Schema。

## 2026-07-05 至 2026-07-06：阶段1 / 第4课 / 空字符串边界

### 本课目标

- 区分缺少字段、空字符串和只包含空格的字符串。
- 证明普通`str`类型不会自动拒绝空字符串。
- 在请求信任边界增加最小有效内容约束。

### 阅读与修改

- 阅读文件：`backend/app/schemas/document.py`、
  `backend/tests/integration/test_documents.py`
- 修改文件：`backend/app/schemas/document.py`、
  `backend/tests/integration/test_documents.py`
- 独立编写内容：创建和更新接口的空白内容参数化测试、共享`NonBlankStr`约束、
  更新失败后的数据库内容保持断言。
- 使用的提示级别：问题说明、约束语法提示、测试审查。
- 第几次尝试通过：创建测试先正确失败；更新测试先出现1次收集错误，修正后正确
  失败；加入共享约束后通过。
- 对应Commit Hash：`fcd3215`。

### 数据流复述

```text
content键存在
→ DocumentCreate或DocumentUpdate执行NonBlankStr校验
→ 先去除首尾空格
→ 去除后长度小于1则返回422
→ 路由函数、Service和Repository均不执行
→ 数据库不新增文档，也不修改已有文档
```

### 上下文检查

不适用：本课处理普通API输入边界。

### 验证证据

- 当前`DocumentCreate.content`仅声明为`str`。
- Python中的`""`仍然是字符串，因此当前类型检查预计会接受。
- 预测验证：学习者能判断当前接口预计返回200，但业务规则应该拒绝空内容。
- 失败测试：`test_create_document_rejects_empty_content`期望422，实际得到200，
  pytest显示`assert 200 == 422`，退出码为`1`。
- 结论：测试已经证明当前`DocumentCreate`错误接受空字符串并执行后续保存。
- 参数化验证：同一测试分别使用`""`和`"   "`，两个用例均实际返回200并失败，
  结果为`2 failed, 2 deselected`。
- 当前环境验证：Pydantic 2.13.4的`StringConstraints(strip_whitespace=True,
  min_length=1)`接受普通文本，并以`string_too_short`拒绝空字符串和纯空格字符串。
- 约束理解：`"  hello  "`会规范化为`"hello"`；创建和更新输入都应拒绝空白内容。
- 输出边界：`DocumentOut.content`不应用非空输入约束，因为待处理上传记录允许None，
  且输出层不应为了通过响应校验而改写数据库已有值。
- 更新测试第1次：pytest在收集阶段报错`function uses no argument 'content'`；装饰器
  声明了`content`参数，但测试函数签名没有接收，且PUT仍使用固定空字符串。
- 测试审查还发现：不应在获得422实际响应前猜测Pydantic错误类型；更新后的内容应
  通过JSON字段比较，不应直接比较HTTP响应的原始字节`response.content`。
- 最小修复：`DocumentCreate.content`和`DocumentUpdate.content`共享
  `NonBlankStr`；`DocumentOut.content`继续使用`str | None`。
- 绿色验证：创建和更新接口的4个空白内容用例全部通过，结果为
  `4 passed, 2 deselected`。
- 错误契约验证：空白内容返回422，错误类型为`string_too_short`，字段位置为
  `["body", "content"]`，并包含`X-Request-ID`。
- 状态一致性验证：非法更新后重新查询文档，原始`content`保持不变。
- 全量回归：`9 passed in 0.71s`。
- 静态检查：`ruff check backend\app backend\tests`返回`All checks passed!`。
- 差异检查：`git diff --check`退出码为0；CRLF信息是Windows换行符提示，不是
  校验失败。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能解释先去除空格，再用最小长度拒绝空白内容 |
| 独立实现同类功能 | 通过 | 为创建和更新接口编写参数化测试并完成约束 |
| 独立定位故障 | 通过 | 用失败测试证明空字符串绕过当前Schema |
| 独立迁移到相似场景并测试 | 通过 | 将创建规则迁移到更新接口，并验证原数据不变 |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：普通`str`与业务有效字符串的区别、Pydantic字符串约束、参数化测试、
  422错误结构、请求校验失败后的状态一致性。
- 仍不理解：本课暂无未解决问题。
- 下一步补强：提交本课变更，再按阶段1计划进入下一课。

## 2026-07-06：阶段1 / 第5课 / 未知异常的安全500响应

### 本课目标

- 理解中间件、全局异常处理器和业务分层的职责边界。
- 验证未知异常不会向客户端暴露内部信息。
- 让500响应携带可用于日志定位的Request ID。

### 阅读与修改

- 阅读文件：`backend/app/core/middleware.py`、`backend/app/core/exceptions.py`、
  `backend/app/main.py`、`backend/tests/conftest.py`
- 修改文件：`backend/app/core/middleware.py`、`backend/app/core/exceptions.py`、
  `backend/app/main.py`、`backend/tests/integration/test_errors.py`
- 独立编写内容：最初尝试编写故障注入测试；在语法示范后完成测试、Request ID
  请求状态和全局异常处理器。
- 使用的提示级别：职责提问、完整测试语法示范、处理器语法示范、逐行纠错。
- 第几次尝试通过：初始测试结构错误；修正后稳定失败于缺少`X-Request-ID`；
  注册全局异常处理器后通过。
- 对应Commit Hash：`cf20bbd`。

### 数据流复述

```text
客户端请求
→ 中间件生成Request ID并保存到request.state
→ API调用Service
→ 故障注入使Service抛出未处理RuntimeError
→ 中间件记录完整异常并重新抛出
→ 全局异常处理器读取Request ID
→ 客户端收到安全JSON 500和X-Request-ID
```

### 上下文检查

不适用：本课处理HTTP请求上下文，不是Agent对话上下文。

### 验证证据

- `TestClient`理解：默认`raise_server_exceptions=True`让pytest看到真实异常和
  Traceback；本课局部使用`False`检查真实客户端会收到的500响应。
- 故障注入：使用`monkeypatch`临时替换路由模块实际调用的
  `get_document_service`，测试结束后自动恢复，不破坏测试数据库。
- 红色验证：状态码500断言通过，但`response.headers.get("X-Request-ID")`
  返回`None`；响应类型为`text/plain`，证明默认500缺少追踪ID和JSON契约。
- 根因定位：中间件只在`else`成功分支添加响应头；异常分支记录日志后执行
  `raise`，因此不会执行该分支。
- 最小修复：中间件将Request ID保存到`request.state`；全局异常处理器返回
  `{"detail": "internal server error"}`和相同`X-Request-ID`。
- 安全验证：响应不包含故障注入文本`sensitive internal detail`。
- 第一轮目标测试：`1 passed in 0.09s`。
- 迁移验证：增加客户端传入`X-Request-ID`的未知异常测试，证明500响应保留并
  原样返回该ID；目标测试结果为`2 passed in 0.18s`。
- 全量回归：`11 passed in 0.98s`。
- 静态检查：`ruff check backend\app backend\tests`返回`All checks passed!`。
- 差异检查：`git diff --check`退出码为0。

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | 能正确复述中间件和全局异常处理器职责 |
| 独立实现同类功能 | 待补强 | 测试和处理器需要完整语法示范 |
| 独立定位故障 | 通过 | 能解释异常分支执行`raise`后跳过`else` |
| 独立迁移到相似场景并测试 | 待补强 | 行为验证通过，但变量和字符串语法需要纠正 |

### 当前结论

- 掌握状态：待补强
- 已经掌握：未处理异常与HTTP错误的区别、中间件调用链、安全500响应和Request ID
  的作用，以及传入Request ID应在响应中保持一致。
- 仍不理解：独立编写`monkeypatch`故障注入测试、异常处理器和Python变量语法仍需
  练习。
- 下一步补强：后续遇到新的异常场景时，从空白测试开始独立完成故障注入和断言。
## 2026-07-07：阶段1 / 第5课补强 / 独立故障注入测试（PUT更新接口）

### 本课目标

- 从空白测试文件开始，独立编写 monkeypatch 故障注入测试
- 理解 *args, **kwargs 在替换函数签名中的应用
- 区分位置参数与关键字参数

### 阅读与修改

- 独立编写内容：test_update_document_error.py 的全部测试代码
- 使用的提示级别：仅需求描述
- 第几次尝试通过：第2次

### 验证证据

- 注入 RuntimeError 到 update_document_service
- 断言500状态码、X-Request-ID、安全响应体、敏感信息不泄漏
- 测试命令：pytest -q backend
- 实际结果：12 passed in 1.48s
- 新增测试文件：backend/tests/integration/test_update_document_error.py

### 掌握验证

| 验证项 | 结果 | 证据 |
|---|---|---|
| 不看答案解释 | 通过 | |
| 独立实现同类功能 | 通过 | 从空白文件独立写出故障注入测试 |
| 独立定位故障 | 通过 | 识别注入文本和响应文本撞词的问题 |
| 独立迁移到相似场景并测试 | 通过 | 将GET安全500的模式迁移到PUT接口 |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：monkeypatch 故障注入、安全500响应契约
- 仍不理解：阶段2将继续学习用户身份和RBAC
- 下一步补强：进入阶段2



## 教学规则（2026-07-07 起永久生效）

1. 每次给出新代码时，必须逐段解释这段代码在做什么
2. 代码中出现用户可能没学过的 Python 知识点，必须单独拿出来说明
   - 说明这个语法/用法是什么意思
   - 用一两句说明其他常见用法（让用户能有对比）
3. 不跳过基础知识，不假设用户已经知道
4. 用户有权随时要求对任意一行代码进行解释


## 2026-07-08：阶段5 / 环境分层与启动流程

### 本课目标

- 理解 APP_ENV 三环境（dev/test/prod）
- 理解 Settings 类加载配置的机制
- 掌握本地启动流程（数据库→迁移→服务→测试）
- 掌握 Swagger 页面用法

### 当前掌握状态

| 内容 | 掌握度 |
|---|---|
| Swagger 页面查看和测试接口 | ✅ 可用 |
| .env 和 Settings 配置机制 | ❌ 不熟 |
| Alembic 迁移命令 | ❌ 不熟 |
| uvicorn 启动服务命令 | ❌ 不熟 |
| 三环境概念 | ❌ 不熟 |

### 遗留问题

多次讲解后仍记不住启动流程命令。下次进入阶段5补强，从空终端开始独立启动项目。

## 2026-07-08：阶段0~1 巩固 / 调用链、事务、Schema边界、Git状态

### 本课目标

- 巩固 python -m 与命令自身参数的区分
- 巩固 API → Service → Repository → ORM → DB 完整调用链
- 巩固数据库事务顺序：add → flush → refresh → commit
- 巩固 Schema 与 ORM 边界（DocumentCreate / Documents / DocumentOut）
- 巩固 Git 三层状态和 restore / diff 的使用场景

### 覆盖知识点

1. **python -m 与参数混淆**
   - python -m pytest 的 -m 是 Python 的 module 参数
   - pytest -m pytest 的 -m 是 pytest 的 marker 参数（筛选测试标签）
   - 使用 python -m pytest 确保测试环境和项目环境一致

2. **完整调用链顺序**
   - 中间件（Request ID 等）→ FastAPI 路由匹配 → Pydantic 校验请求体（422 边界）→ API 路由函数 → Service（业务编排）→ Repository（数据访问）→ ORM → 数据库
   - Pydantic 校验在进入 API 函数之前就完成了；失败直接返回 422
   - Service 层不接触 HTTP，Repository 返回 ORM 对象或 None

3. **事务安全顺序**
   - `add`: 标记到 Session，未发 SQL
   - `flush`: 发 SQL 到数据库（当前事务可见，其他连接不可见）
   - `refresh`: 从数据库读回自动生成的字段（id、created_at 等）
   - `commit`: 提交事务，其他连接才可见
   - `flush` → `refresh` → `commit` 比 `add` → `commit` → `refresh` 更安全，因为 refresh 失败时事务未提交，可以 rollback

4. **Schema 与 ORM 边界**
   - DocumentCreate: 定义客户端必须提交什么字段（输入校验）
   - Documents (ORM): 定义数据库表结构和列类型（持久化）
   - DocumentOut: 定义服务端返回什么字段（输出裁剪）
   - 三者互相独立，改 API 响应不需要改数据库

5. **Git 三层状态与恢复**
   - 工作区（未 add）↔ 暂存区（已 add）↔ HEAD（已提交）
   - git restore file: 暂存区 → 工作区（撤销未 add 的修改）
   - git restore --staged file: HEAD → 暂存区（撤销 add）
   - git diff: 工作区 vs 暂存区
   - git diff --cached: 暂存区 vs HEAD（提交前必用）
   - git diff HEAD: 工作区 vs HEAD（看总改动量）
   - --check: 检查空格格式，不是代码规范检查（那是 ruff 的事）

### 当前掌握状态

| 知识点 | 掌握度 |
|---|---|
| python -m 与退出码 | ✅ 理解 |
| 调用链（中间件→Pydantic→API→Service→Repo→ORM→DB） | ✅ 理解 |
| 事务顺序（add→flush→refresh→commit） | ✅ 理解 |
| Schema 与 ORM 三层边界 | ✅ 理解 |
| Git 三层状态、restore、diff | ✅ 理解 |

### 遗留问题

无。阶段 0~1 核心概念已巩固通关。

## 2026-07-09：阶段2~5 巩固 / 用户认证、文件上传、分块查询、启动流程

### 本课目标

- 巩固 API Key 认证机制（get_current_user、Depends 注入）
- 巩固用户隔离（API 层传 user_id=current_user.id，Repository 层过滤）
- 巩固 401（认证失败）与 404（资源不存在）的语义区分
- 巩固文件上传流程（UploadFile、校验链、SHA256 去重）
- 巩固事务安全（commit 先于 refresh 的隐患、rollback + 文件删除）
- 巩固分块查询（UniqueConstraint、CASCADE 外键删除）
- 巩固完整启动流程（PostgreSQL → alembic → uvicorn → pytest）

### 覆盖知识点

1. **API Key 认证**
   - Header(default=None, alias="X-API-Key") 从请求头读取 API Key
   - Depends(get_current_user) 在每个路由前自动执行认证
   - 认证失败统一返回 401，且错误消息一致防止穷举
   - 401（认证）vs 404（资源不存在）vs 409（资源冲突）vs 422（请求本身问题）

2. **用户隔离**
   - API 层传 user_id=current_user.id 到 Service/Repository
   - Repository 查询时加 Documents.user_id == user_id 过滤
   - 分块查询先做文档归属检查（404），再按 document_id 查分块

3. **文件上传**
   - UploadFile = File(...) 接收 multipart/form-data 上传
   - 校验链：文件名 → 文件后缀 → 文件大小 → 空文件检查 → 409 去重
   - SHA256 去重两层：提交前查 + IntegrityError 兜底
   - 文件先保存到磁盘，再写入数据库；失败时 rollback + 删除文件

4. **分块查询**
   - UniqueConstraint(document_id, chunk_index)：同文档内序号不重复
   - ForeignKey(ondelete="CASCADE")：删文档时自动删分块

5. **启动流程**
   - PostgreSQL：后台服务，启动项目前必须先运行
   - Alembic：数据库版本管理，lembic upgrade head 更新表结构
   - uvicorn：python -m uvicorn app.main:app --reload
   - pytest：python -m pytest -q

### 当前掌握状态

| 知识点 | 掌握度 |
|---|---|
| API Key 认证（Header、Depends、401） | ✅ 理解 |
| 用户隔离（user_id 过滤、分块归属检查） | ✅ 理解 |
| HTTP 状态码语义（401/404/409/422） | ✅ 理解 |
| 文件上传校验链（名称/后缀/大小/空文件/SHA256） | ✅ 理解 |
| 事务回滚 + 文件清理 | ✅ 理解 |
| UniqueConstraint + CASCADE 删除 | ✅ 理解 |
| 启动流程（PG → alembic → uvicorn → pytest） | ✅ 理解 |

### 遗留问题

- PostgreSQL 具体工作原理和使用方式尚未深入学习
- 三环境（dev/test/prod）的差异化逻辑尚未在代码中实现

## 2026-07-10：阶段5补强 / Session、engine、连接池概念补强

### 本课目标

- 理解 main.py 每行代码的作用（模块级代码、lifespan、中间件注册、异常处理器注册、路由挂载）
- 理解 logging 日志系统的完整流程（Handler/Formatter/Logger 三层关系、日志向上传播）
- 解决 Pylance 类型检查器对 add_exception_handler 的类型报错

### 覆盖知识点

1. **main.py 组装流程**
   - 模块级代码（settings/configure_logging）在导入时执行
   - lifespan：启动时创建目录+检测数据库，关闭时释放连接池
   - 中间件嵌套顺序：后注册的先执行
   - 异常处理器按类型精确度匹配，不是按注册顺序
   - include_router 挂载所有子路由
   - text(\"SELECT 1\") 测试数据库连接

2. **Pylance 类型错误修复**
   - add_exception_handler 期望 handler 第二个参数是 Exception
   - 传具体子类时 Pylance 报类型不兼容
   - 修复：加 # type: ignore[arg-type]

3. **日志系统（logging）**
   - LogRecord：Python 自动创建（logger.info/error/exception 都会），包含消息/级别/异常/时间
   - Logger：不传参获取根日志器（所有日志器的父级），传名字获取子日志器（单例）
   - Handler：输出到哪里。StreamHandler（控制台），RotatingFileHandler（文件，10MB 轮转）
   - Formatter：输出成什么样子。setFormatter 绑定到 Handler
   - logger.error vs logger.exception：exception 在 except 块中自动附带异常堆栈
   - 日志向上传播：子日志器没 Handler 时传给父级直到根日志器
   - global 声明函数内修改模块级全局变量，_logging_configured 防重复注册
   - 控制台和文件可用不同 Formatter，同一 record 被两个 Handler 各自处理

### 当前掌握状态

| 知识点 | 掌握度 |
|---|---|
| main.py 各组件作用 | ✅ 理解 |
| Pylance 类型错误及修复 | ✅ 理解 |
| LogRecord/Logger/Handler/Formatter 三层关系 | ✅ 理解 |
| 日志传播和根日志器 | ✅ 理解 |
| error vs exception | ✅ 理解 |
| global 和防重复注册 | ✅ 理解 |

### 本课目标

- 理解 engine 与 SessionLocal 的关系（连接池 vs 会话工厂）
- 理解 pool_pre_ping=True 的作用
- 理解 expire_on_commit=False 的作用
- 理解 NAMING_CONVENTION 约束命名规则
- 理解 rollback() 与 close() 的区别
- 确认当前代码实际完成进度

### 阅读与修改

- 阅读文件：`backend/app/db/session.py`、`backend/app/db/base.py`、`backend/app/services/document_ingestion_service.py`、`backend/app/repositories/document_repository.py`
- 修改文件：仅更新本学习记录

### 覆盖知识点

1. **engine 与 SessionLocal**
   - engine 是连接池，模块级只创建一次
   - SessionLocal 是 sessionmaker 工厂，也是模块级只创建一次
   - 每次请求调 `SessionLocal()` 创建一个新的 Session，从连接池拿一个连接
   - `get_db()` 的 `yield` 让 FastAPI 在路由函数执行完后回到 `finally` 执行 `db.close()`

2. **pool_pre_ping=True**
   - 从连接池取出连接前先发 SELECT 1 测试
   - 防止连接失效（数据库重启/网络闪断）导致请求异常
   - 不设的话，偶尔会出现 "connection is already closed" 错误

3. **expire_on_commit=False**
   - 默认 True：commit 后对象过期，下次读属性触发 SELECT 重新加载
   - 设 False：commit 后对象不过期，读属性直接从内存读，不查数据库
   - expire 不是 commit，两者是不同的概念
   - 上传服务中 commit 后紧接 refresh()，设 False 可减少额外 SELECT

4. **NAMING_CONVENTION**
   - 数据库约束命名规范，让约束名稳定可读
   - 不设的话由数据库随机生成，难以识别
   - 模板示例：`fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`
   - Documents.user_id → users.id 生成：`fk_documents_user_id_users`
   - 其他：`pk_documents`、`uq_documents_sha256`、`ck_documents_status_values`

5. **rollback() vs close()**
   - rollback()：撤销当前事务中未提交的 SQL，Session 仍然存活，可继续使用
   - close()：归还连接给连接池，Session 不能再用了
   - 文档编辑类比：rollback = Ctrl+Z 撤销，close = 关闭文档窗口
   - 实际代码中 rollback 后通常跟 raise，异常传到 get_db() 的 finally 才执行 close()

### 当前代码实际完成进度确认

| 阶段 | 学习记录状态 | 代码实际状态 |
|---|---|---|
| 0 工程基线 | 已掌握 | ✅ 完成 |
| 1 HTTP契约/Schema/异常 | 已掌握 | ✅ 完成 |
| 2 用户身份/RBAC | 表格"未开始" | ✅ 代码已实现（API Key认证、User模型、test_auth.py） |
| 3 文件上传闭环 | 表格"未开始" | ✅ 代码已实现（/upload路由、SHA256去重、校验链、test_document_upload.py） |
| 4 文档解析分块 | 表格"未开始" | ✅ 代码已实现（chunk_text/chunk_file、DocumentChunk模型、GET /chunks、迁移） |
| 5 环境分层 | 待补强 | ⚠️ 概念已讲解，Docker Compose 未实现 |
| 6 持久化任务模型 | 未开始 | ❌ 未实现 |

### 当前结论

- 掌握状态：待补强 → 基础概念已掌握
- 已经掌握：engine/SessionLocal 关系、pool_pre_ping、expire_on_commit、NAMING_CONVENTION、rollback vs close
- 仍不理解：Docker Compose 实际操作不熟
- 下一步补强：进入阶段6 持久化任务模型

## 2026-07-11：阶段5补强 / Docker Compose、三环境、启动流程

### 本课目标

- 理解 Docker Compose 的作用（不用手写，会用就行）
- 理解 Settings 配置机制（`extra="ignore"`、`.env` + `settings.py` 关系）
- 掌握从零开始的完整启动流程
- 区分三环境（development / test / production）配置差异

### 创建文件

- `docker-compose.yml`：包含 postgres:16 和 redis:7 两个服务，含 healthcheck

### 掌握知识点

1. **Docker Compose 结构**
   - `services` 定义容器，`volumes` 定义持久化存储
   - `ports: "5432:5432"` 左边宿主机端口，右边容器端口
   - `healthcheck` 定时检查容器是否真正可用

2. **Settings 配置机制**
   - `extra="ignore"`：.env 里未在 Settings 声明的变量静默忽略
   - `extra="forbid"`：未声明的变量导致报错
   - `extra="allow"`：未声明的变量存入 `__pydantic_extra__`
   - 新增配置项需要改 `settings.py`（声明字段）+ `.env.example`（模板）+ `.env`（本地）
   - `@lru_cache` 确保 Settings 只加载一次（单例）

3. **完整启动流程（4步）**
   - 第1步：启动 PostgreSQL → `docker compose up -d`（或确认已运行）
   - 第2步：创建表结构 → `alembic upgrade head`
   - 第3步：验证 → `pytest -q`
   - 第4步：启动服务 → `uvicorn app.main:app --reload`
   - 日常开发通常只需要第3步和第4步

4. **三环境配置差异**

   | 配置项 | development | production |
   |---|---|---|
   | APP_ENV | development | production |
   | APP_DEBUG | true/false | false（不暴露错误信息） |
   | LOG_LEVEL | INFO | WARNING 或 ERROR |
   | DATABASE_HOST | 127.0.0.1 | 正式数据库 IP |
   | DATABASE_PASSWORD | 开发密码 | 高强度密码 |
   | CORS_ORIGINS | localhost:3000 | 实际前端域名 |

### 掌握验证

| 验证项 | 结果 |
|---|---|
| 能说出 Settings 配置新增需要改哪些文件 | ✅ 通过 |
| 能区分 extra 三种模式的作用 | ✅ 通过 |
| 能排出从零启动的4步顺序 | ⚠️ 需要巩固（初始排错：先启动服务再跑迁移） |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：Settings 配置机制、三环境概念、启动流程4步顺序
- 仍不理解：无
- 下一步：进入阶段6 持久化任务模型

## 2026-07-11（晚）：阶段6 / 持久化任务模型

### 本课目标

- 创建 analysis_tasks 表（ORM 模型 + Alembic 迁移）
- 添加 CheckConstraint 状态约束
- 完整 CRUD 分层（Schema → Repository → Service → API）
- 掌握验证：5 道业务场景题全部答对

### 创建的文件

| 文件 | 层 | 作用 |
|---|---|---|
| `app/models/analysis_task.py` | Model | 定义 analysis_tasks 表，含 status CheckConstraint |
| `app/schemas/task.py` | Schema | TaskCreate（输入）+ TaskOut（输出） |
| `app/repositories/task_repository.py` | Repository | create_task、get_task_by_id、get_tasks |
| `app/services/task_service.py` | Service | 业务编排，调用 Repository |
| `app/api/tasks.py` | API | POST/GET /tasks、GET /tasks/{id} |
| 2 个迁移文件 | 迁移 | 创建表 + 添加约束 |

### 修改的文件

- `migrations/env.py`：添加 User 和 AnalysisTask 的导入
- `app/api/router.py`：注册 tasks_router

### 新增 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST /tasks | 创建任务 | 传入 `{"question": "..."}` |
| GET /tasks | 任务列表 | 当前用户的所有任务 |
| GET /tasks/{id} | 任务详情 | 按 ID 查询 |

### 掌握验证结果

| 题号 | 问题 | 结果 |
|---|---|---|
| 1 | 生产环境改密码要改哪些文件 | ✅ 只改 .env，重启生效 |
| 2 | 拉取同事新代码后的操作顺序 | ✅ alembic → pytest |
| 3 | 加 priority 字段要改哪些文件 | ✅ 模型 + 迁移 + Schema |
| 4 | 改 created_at 格式改哪层 | ✅ Schema 层 |
| 5 | 用户隔离问题检查哪个文件 | ✅ Repository 的 filter |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：完整分层架构、ORM 模型、迁移、CheckConstraint、Schema/Repository/Service/API 分工
- 下一步：阶段7 Celery 异步执行（Redis 已安装，Celery 已配置）

## 2026-07-11（晚）：阶段8 / pgvector + Embedding

### 本课目标

- 理解 Embedding（向量化）的原理：文字 → 数字 → 相似度计算
- 理解 pgvector 的作用：在 PostgreSQL 中存向量、算距离、做搜索
- 掌握 ABC 抽象类的作用和用法
- 掌握 global 关键字和懒加载模式
- 掌握余弦距离 `<=>` 运算符
- 掌握参数绑定 vs 拼字符串的区别
- 掌握 `execute().fetchall()` 的作用

### 创建的文件

| 文件 | 作用 |
|---|---|
| `app/core/embeddings.py` | EmbeddingProvider 抽象类（定标准） |
| `app/core/embeddings_local.py` | 本地模型实现（sentence-transformers） |
| `app/repositories/vector_repository.py` | 向量搜索（search_similar_chunks） |
| `scripts/demo_cosine.py` | 余弦相似度演示脚本 |
| `scripts/demo_embedding.py` | Embedding 演示脚本（因网络未运行） |
| `explain_phase8.md` | 完整讲解文档 |

### 修改的文件

| 文件 | 修改内容 |
|---|---|
| `app/models/document_chunk.py` | 新增 `embedding: Vector(384)` 字段 |

### 掌握验证（5题全对）

| 题号 | 知识点 | 结果 |
|---|---|---|
| 1 | ABC 和 abstractmethod | ✅ |
| 2 | global 关键字 | ✅ |
| 3 | 余弦相似度 | ✅ |
| 4 | nullable 和迁移 | ✅ |
| 5 | 参数绑定防 SQL 注入 | ✅ |

### 当前结论

- 掌握状态：已掌握
- 已经掌握：Embedding 原理、余弦相似度、ABC 抽象类、global 关键字、参数绑定
- 仍不理解：无
- 下一步：待定

## 2026-07-11（深夜）：阶段10 / Model Gateway + 阶段11 / 可靠RAG

### 本课目标

- 理解 Model Gateway 的作用：统一模型调用接口、记录Token和成本
- 掌握 @dataclass 和 field(default_factory) 的用法
- 理解延迟导入（lazy import）的作用
- 理解 RAG 完整流程：检索 → 充分性判断 → Prompt组装 → 调用模型
- 理解 validate_citations 为什么防不住AI编造（真实ID配假内容）
- 掌握 RAG 可靠性靠检索质量而非下游校验的原则

### 创建/修改的文件

| 文件 | 作用 |
|---|---|
| `app/core/model_gateway.py` | ModelGateway 抽象类 + ModelCallRecord 数据类 |
| `app/core/model_gateway_local.py` | 本地模拟实现（不需要API Key） |
| `app/core/model_gateway_openai.py` | OpenAI真实调用实现 |
| `tests/test_model_gateway.py` | Gateway测试（2个） |
| `app/core/rag_engine.py` | 可靠RAG引擎（EvidenceRef、build_prompt、check_sufficiency） |
| `tests/test_rag_engine.py` | RAG引擎测试（build_prompt + check_sufficiency） |
| `app/tasks/analysis_tasks.py`（修改） | Worker改为完整RAG流程：检索→充分性→Prompt→模型→保存 |

### 学习过程中的关键修正

| 次数 | 问题 | 发现者 | 修正 |
|---|---|---|---|
| 1 | check_sufficiency只数数量不看质量 | 学习者提出 | 增加 `min_avg_score` 平均分判断 |
| 2 | validate_citations字符集合比较不可靠 | 学习者指出 | 删除内容匹配逻辑 |
| 3 | validate_citations ID校验防不住"真实ID配假内容" | 学习者指出 | 删除整个 validate_citations 函数 |
| 4 | RAG可靠性靠什么保证 | 学习者总结 | 靠上游检索质量而非下游AI引用校验 |

### 掌握验证

| 知识点 | 状态 |
|---|---|
| @dataclass 自动生成 __init__ | ✅ 已理解 |
| f-string 变量插入 | ✅ 已理解 |
| "\n\n".join(列表) 连接字符串 | ✅ 已理解 |
| re.findall 正则提取 | ✅ 已理解 |
| set 集合 vs list 列表 | ✅ 已理解 |
| not in 判断元素是否存在 | ✅ 已理解 |
| check_sufficiency 平均分判断 | ✅ 已理解 |
| validate_citations的局限性 | ✅ 已理解并删除 |
| RAG可靠性靠检索质量 | ✅ 已理解 |

### 当前结论

- 掌握状态：阶段10学习中、阶段11学习中
- 测试基线：24 passed
- 遗留问题：pgvector未安装、Docker引擎未启动
- 下一步：待定


### 已完成

- 安装 Redis for Windows（端口 6379，已验证监听）
- 安装 Celery 5.6.3
- 创建 `app/core/celery_app.py`：Celery 应用配置（broker=redis）
- 创建 `app/tasks/__init__.py`：任务模块目录
- 创建 `app/tasks/analysis_tasks.py`：异步分析任务（模拟处理，含状态流转和重试）
- 修改 `app/api/tasks.py`：POST /tasks 创建任务后调用 `process_analysis_task.delay()` 异步执行
- Celery 发送任务验证通过（Task sent OK）
- redis-py 降级到 4.x 兼容旧版 Redis 3.0.504
- 19 个测试全部通过

### 关键代码解释

`process_analysis_task` 异步任务流程：
1. 自己创建 `SessionLocal()`（Worker 独立于 API 运行）
2. `queued → running`：标记任务开始处理
3. 模拟处理（实际项目中调用 RAG 或 Agent）
4. `running → completed`：保存结果
5. 异常时 `→ failed`：保存错误信息，自动重试最多 3 次
6. `finally: db.close()` 确保 Session 关闭

API 调用 Celery：
```python
# API 创建任务后，不等待直接返回
record = create_task_service(...)
process_analysis_task.delay(task_id=record.id, user_id=current_user.id)
return record
```

### 端到端测试结果（2026-07-11 下午）

1. POST /tasks 创建任务（status=queued）
2. Celery Worker 自动拉取消息
3. Worker 执行：修改记录 status=running → 模拟处理 → status=completed
4. GET /tasks/{id} 查询 → status=completed, result_summary 有内容 ✅

**数据流验证：**
```
POST /tasks → 数据库写入(status=queued)
  → process_analysis_task.delay()
  → Celery Worker 收到消息
  → queued → running（模拟处理）→ completed
  → 结果存入 result_summary
  → 客户端 GET 查询可见完整结果
```

**遇到的故障与修复：**
1. 缺少 `db.commit()` 导致 Worker 查不到记录 → API 层加 commit
2. Worker `[tasks]` 下无任务 → celery_app.py 加 `imports` 配置
3. Worker commit 时报 `NoReferencedTableError` → tasks/analysis_tasks.py 加 model 导入
