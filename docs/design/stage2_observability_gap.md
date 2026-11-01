# 工单 2.1：任务追踪能力调查（2026-11-01）

本工单只读调查已有实现，不代表阶段 1 或阶段 2 验收通过。

| 原计划要求 | 可复用实现 / 当前证据 | 缺口 |
|---|---|---|
| 按 task_id 串起链路 | backend/scripts/evaluation/render_task_trace.py 的 load_trace，读取任务、尝试、事件、模型和工具记录 | CLI 还要求 company_id，这是应保留的租户范围约束 |
| 时间线、状态迁移、重试 | render_trace_html 按时间排序，含 attempt 编号、retry_number、状态和错误码 | 尚未证明事件覆盖所有 API→Outbox→Worker 环节 |
| 模型名、token、耗时 | 模型行输出 provider/model、duration_ms、tokens/cost | 没有明确 billing_status 或任务/步骤费用汇总；未知费用不可当零 |
| 工具参数和结果摘要、SQL、chunk 编号 | 当前明确排除载荷，工具行只有名称、状态、错误码和耗时 | 与 2.2 所需诊断字段有差距；应先确定脱敏后的字段白名单，不直接输出原始载荷 |
| 关联 ID 与 JSON 日志 | 本次只调查追踪脚本，未审计全链日志 | request_id/task_id/attempt 贯穿情况未验证；此前 Worker 控制台为纯文本 |
| 密钥、邮箱、手机号脱敏测试 | 已有测试证明不输出问题、prompt、SQL、工具结果，HTML 元数据转义 | HTML 转义只能防注入，不等于隐私脱敏；尚无本工单密钥/邮箱/手机号完整验证 |
| 成本与耗时汇总 | 冒烟已有单题总耗时、token、费用；trace 有各条记录耗时 | 步骤汇总、未知费用状态和模型重试统计未提供 |

## 本次验证

- 在 backend 目录执行 `..\.venv\Scripts\python.exe -m pytest tests/scripts/test_render_task_trace.py -k excludes_payloads -x -q`：1 passed、1 deselected。首次从根目录执行因 scripts.evaluation 导入冲突收集失败；调整工作目录后通过，未修改代码。
- 对运行库使用只读事务，调用现有 load_trace/render_trace_html 导出 205（company 115）：1 次尝试、19 条事件、8 条模型记录、2 条工具记录，最终 awaiting_review 可见。
- 将同任务查询范围改为 company 116，现有加载器抛出 ValueError；未修改数据库或调用模型。
- 本地输出 artifacts/smoke/task-205-trace-stage2.html；这只是助手验证，不替代用户选任务并在 5 分钟内定位故障的阶段出口验收。

## 下一工单建议

复用现有脚本，先为元数据建立敏感信息测试，再按真实记录结构补必要的安全摘要。不要新建另一套追踪工具，也不要为展示方便放宽租户隔离。权限、主链或评分若需变化，先单独确认。
