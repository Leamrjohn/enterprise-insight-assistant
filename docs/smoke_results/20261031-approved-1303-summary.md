# 最新修复后单轮重测

- 用户授权一轮最多 8 题/$0.20/30 分钟；2026-10-31 13:02:54 EDT 开始预检，代码 336405e。用户的 AGENTS.md 修改与未跟踪会话回顾文档保留，backend 无未提交改动；运行身份检查通过，预检 13 服务运行且 API readiness=True。
- 后台运行 `python backend/scripts/evaluation/run_smoke_tests.py --run-id 20261031-approved-1303`，只读结果文件跟踪；退出文件为 0，末事件 done。普通非成功结果停止，待人工复核保留非成功并继续，不自动批准。
- 完整提交 189–196 共 8 题：7 成功、1 失败（195 awaiting_review）、结果错误 0、无响应 0；成功率 87.5%，退出 0 代表运行完整而非全题通过。
- 整轮 95.3 秒，57,060 token，估算费用 $0.021499。只读数据库核对 42 条调用账本全部 settled，无空费用，合计与执行器相同；供应商账单未核对。
- 复核请求 20 pending，publication=awaiting_human_review/causal_hypothesis_requires_human_review，仅有 report_draft、无 report。第 8 题 needs_clarification 符合原期望。
- 此前失败的销售额题和质量文档题本轮分别 completed；只能证明本次样本符合期望，不能单独归因于某一修复，也不能证明日期文件名误判等所有变体已解决。预算停止分支本轮未触发。
- 已部署 SQL 复核映射、chunk_id 引用识别及 Planner 预算异常传播；本轮没有更改评分期望、业务权限或预算。未启动第二/第三轮，旧版本结果不拼入当前三轮基线。
- 原始事件、进程日志、退出码及只读核账保存于 artifacts/smoke/20261031-approved-1303*；同名 Markdown 为完整逐题结果。
