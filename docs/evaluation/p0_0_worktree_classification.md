# P0-0 工作区差异分类表

> 状态：`prepared`。本表记录当前可验证事实和准备阶段的建议处置；尚未执行清理、提交或删除。
> 目标：在不清理、不提交、不覆盖现有改动的前提下，把基线、候选、评测工具和无关改动分开。

## 当前验证事实

- Git 基线：`53723fb48a36b6235e0ecf04e04c3c2cdb182f8c`（`v2.1.0`）。
- 隔离环境：Python `3.13.14`，项目解释器为 `.venv-py313/Scripts/python.exe`。
- 干净 HEAD：`338 tests collected`；非 E2E、非 slow 为
  `332 passed, 2 skipped, 4 deselected`。
- 当前工作区：`333 tests collected`；非 E2E、非 slow 为
  `326 passed, 2 skipped, 5 deselected`。
- HEAD Ruff 有 `337` 项，当前工作区有 `301` 项；不能把当前全部 Ruff
  结果归因于候选。当前新增的 7 个 `F401` 均来自未完成的
  `backend/app/models/taskspec.py`。
- 当前没有“真实持久化任务 -> EvaluationObservation”的适配器；现有业务评测脚本
  不调用 Agent，`workflow_evaluation` 只聚合已存在的任务状态和 Tool 审计。
- 当前共有 243 个变更路径；按下面八组归类后没有未覆盖路径。这里的数量只是
  工作区清点，不代表 243 项独立功能变更。

## 分类方法

每组必须分别填写两个维度，不能用一个标签同时表达处置和评测角色。

1. **处置维度**：`保留改动` / `丢弃改动` / `确认删除目标` /
   `无关用户改动` / `未决`。其中“丢弃改动”表示恢复原文件或删除未跟踪候选，
   “确认删除目标”表示文件删除本身就是要保留的产品改动。
2. **证据维度**：`baseline` / `candidate` / `shared_harness` /
   `governance_record` / `non_comparison`。当前只有干净 HEAD 是 baseline；
   未提交文件不能因为“准备保留”就被称为 baseline。

## 准备阶段分类结论

| 组 | 主要范围 | 已验证证据 | 处置维度 | 证据维度 | owner / 意图 |
|---|---|---|---|---|---|
| A | `archive/legacy-and-artifacts-2026-07-26/**` 的 44 个删除 | 该归档由提交 `c46071d` 主动建立；当前非 archive 文件未发现引用，但这不能证明本次删除意图 | 未决；暂不操作 | non_comparison | 历史归档的再次删除没有可验证 owner/决策记录 |
| B | Todo、Label、Prompt Template 的 API/Model/Repository/Schema/Service/Test 删除，共 22 个路径 | 当前 Router 已移除三组路由，并有 OpenAPI 测试断言产品不暴露这些训练 CRUD | 确认删除目标 | non_comparison | 产品边界清理；删除训练 CRUD，不属于 RAG 候选收益 |
| C | RAG、Embedding、Vector Repository、知识库 manifest、新增语料和对应检索评测，共 132 个路径 | `candidate_scope_v1.md` 明确把核心路径列为检索候选；尚未证明最终报告质量提升 | 保留改动，等待独立评测 | candidate | 检索候选；只能通过冻结语料和同环境比较晋升 |
| D | 业务评测 Schema/Service/Test、评测镜像、审计脚本和评测文档，共 14 个路径 | 可收集并运行确定性测试，但尚未接入真实 Worker Observation | 保留并修正契约缺口 | shared_harness | P0-0 比较工具；必须对 baseline/candidate 使用同一版本 |
| E1 | `backend/app/models/input_artifact.py` | 设计账本将它记录为“未迁移的候选 ORM 根模型”；尚无版本模型、迁移、上传链路或契约测试 | 保留为未实现候选，不接入迁移 | candidate | P0-IN 后续切片，不计入当前已实现能力 |
| E2 | `backend/app/models/taskspec.py` | 已确认设计禁止在 InputArtifactVersion/DocumentVersion 契约前创建 TaskSpec；当前文件仅有 id 且产生 7 个 F401 | 丢弃改动；本轮暂不删除 | non_comparison | 提前且不完整的空壳，不应继续扩写 |
| F | core/ML Worker 镜像拆分、依赖拆分、Compose、环境模板和 Runbook，共 8 个路径 | 目标是把 PyTorch 与本地模型依赖移出轻量 API 镜像；尚未完成镜像构建和真实栈验证，Runbook 当前还存在重复一级标题 | 保留改动，等待容器验证 | candidate | 运行时依赖隔离候选；与 RAG 算法候选分别验收 |
| G1 | `.gitignore`、`AGENTS.md`、产品/README、安全/贡献文档、确认设计与主路线图，共 8 个路径 | 当前 AGENTS、确认设计和路线图已被本会话明确选为规则来源；其他文档仍需分别验证内容 | 保留改动 | governance_record | 项目规则与目标设计，不作为算法候选指标来源 |
| G2 | 旧计划、旧教学文档和旧 docs 索引删除，共 10 个路径 | 新路线图意图统一规则来源；尚未逐项证明旧文档中的有效信息已迁移 | 确认删除目标；提交前复核迁移 | governance_record | 去除冲突规则来源，提交前仍需检查有效信息是否丢失 |
| H1 | `backend/app/services/workflow_graph.py` 冗余条件删除 | 两个分支原来都返回 `planning_failure_node`，当前修改是行为等价化简 | 保留改动 | non_comparison | 等价清理，不应影响候选指标结论 |
| H2 | `backend/tests/test_workflow.py` 仅增加文件尾空行 | 没有行为变化，并导致 `git diff --check` 报错 | 丢弃改动；本轮暂不修改 | non_comparison | 无意图的空白差异 |
| H3 | `backend/scripts/lirbary.py` 删除 | 脚本属于无关图书示例并硬编码本地数据库凭据；当前产品代码与测试未引用它，但删除意图仍需确认 | 确认删除目标 | non_comparison | 删除无关且不安全的历史示例脚本 |

## 进入下一步的门禁

- A 组保持未决并从候选比较中隔离；其余组已有准备阶段处置与证据角色；
- 不能因测试数量变少或 Ruff 总数变少就接受候选；
- 不自动清理、格式化、提交或删除任何未确认改动；
- 分类完成后，才冻结 baseline manifest，并设计最小的真实任务 Observation Adapter。
