# 阶段 1.1：冒烟能力复用清单

调查日期：2026-10-28；代码基线：1b3745c。本次只读调查与离线分类检查，没有创建租户、提交问题或调用模型。

## 可复用

| 能力 | 当前实现与证据 | 使用边界 |
|---|---|---|
| 8 个固定问题 | `backend/scripts/evaluation/run_smoke_tests.py` 的 IDS；3 data_only、3 knowledge_only、1 hybrid、1 needs_clarification | 包含指定 delivered 收入题；保留原用例期望 |
| 用例与评分 | `development_case_selection.json` 定位既有 fixture；`evaluate_case` 消费持久化 Observation | oracle_review 仍 pending；不是独立留出评测 |
| 测试身份与数据源 | `_bootstrap_tenant` 创建独立公司/成员；临时用户名和密码用于 HTTP 登录；`_create_source_snapshot` 发现只读演示库 Schema | 会写平台库的测试资源，不是纯只读运行；没有必要复用个人账号 |
| 文档夹具 | 校验语料 manifest 哈希，通过已有文档内容接口创建并等待处理 | 准备文档可能触发本地嵌入；不新增文件上传入口 |
| HTTP 主流程 | 登录→建会话→提交问题→轮询任务；评分读取持久化任务 | 每题 180 秒，超时尝试取消，传输或取消不确定时停止 |
| 四类结果 | 成功、结果错误、失败、无响应；预期澄清由原评分器判断 | `--self-test` 本次 5 条断言通过，不证明真实模型效果 |
| 运行证据 | `2026-10-28.md` 与 `artifacts/smoke/2026-10-28.json` | 本次重新汇总：第 1 轮 8 个结果均失败，最后事件 stop；第 2、3 轮未运行 |

任务状态共有 queued、running、retrying、awaiting_review、completed、partial、failed、cancelled、needs_clarification。
当前 runner 将最后五种作为终态；awaiting_review 会继续等待并可能超时，不等同于成功或失败。

## 1.2 必须补齐的执行与记录缺口

1. **首轮人工门禁**：`range(start_round, 4)` 会在费用和耗时检查通过后自动继续后续轮次，不满足“先报第 1 轮，再决定继续”的要求。默认只运行获准轮次。
2. **运行身份记录**：现有报告只有 Git、fixture 哈希和结果用量，没有完整模型名/参数、语料版本/seed、业务数据版本证据；不能据此宣布可重复基线。
3. **续跑一致性**：续跑按日期读取事件并仅校验结果数量，报告头使用当前 Git；未阻止不同代码、用例或数据混入同一基线。必须比对冻结的运行身份，旧结果缺少身份时拒绝续拼。

不修改评分期望、不扩充用例、不另建评测框架。历史 HTTP 402 来自既有日志记录，本次未重验余额；恢复模型和付费运行仍需成本/时间授权。
8 个仓库外留出题由用户与 Claude 保管，本次未读取或创建。阶段 0 用户/学习验收仍未确认；本调查不代表阶段 0 或 1 整体通过。
