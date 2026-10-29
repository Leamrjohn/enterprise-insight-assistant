# 同步时钟后重测结论

- 代码基线：`ac6072d`；沿用用户单轮最多 8 题、$0.20、30 分钟授权，预检起点 2026-10-29 07:33 EDT。
- AWS 原生签名验证：STS 与 HeadBucket 均成功，服务器时差不到 1 秒；仅重建 API、Worker、report-worker、beat 以加载两项新凭据，不执行迁移或重建数据库；13 个常驻服务运行，API readiness=True。
- `20261029-clock-fixed-0734`：首份文档 180 秒内未完成，执行器 HarnessError 退出 1，业务任务数 0；后台文档 66 后续 completed，Worker 无活动任务后才重新启动测试。
- `20261029-warm-ready-0738`：提交 7 题，现有评分通过 4 题、无响应 3 题、第 8 题未提交；最后事件为 transport_or_cancellation_uncertain，未产生完整 round/done，不可作为完整三轮基线或续跑。

| 任务 | 运行内结果 | 后续只读状态 | 失败层／证据 |
|---|---|---|---|
| 163–165 | 3 道数据题通过 | completed / completed / partial | 现有评分无 violations |
| 166 | 知识题无响应 | cancelled | Knowledge 工具调用记录 443032 ms；现场日志显示重排模型加载，但不能把全部耗时都归于下载 |
| 167 | 知识题无响应 | cancelled | queued 阶段超时，未记录模型调用 |
| 168 | 知识题通过 | completed | 现有评分无 violations |
| 169 | 混合题无响应，取消失败 | awaiting_review | pending 复核原因 causal_hypothesis_requires_human_review；取消服务只允许 queued/running/retrying |

- 只读最终模型账本：34 条调用记录（包含本地零费用调用），47,609 token，$0.018040，全部 settled；供应商实际账单未核对。
- 调用记录时间为 11:38:11–11:46:37 UTC，执行器记录的逐题等待共约 680.8 秒；最后只读核查在 17:41 UTC 后，未重新调用模型。原终端句柄已失效，不能重新取得最终进程退出码；停止状态由事件及数据库证实。
- 超时任务 166 在取消请求后仍产生后续模型调用，最终费用高于超时快照；保留原始报告，不覆盖即时测量值。待办：检查取消传播及最终费用收集。
- 当前 Worker 无活动任务，169 仍为待人工复核，不擅自批准、拒绝或绕过门禁。awaiting_review 不等于程序崩溃；执行器等待／取消契约与此状态不匹配，需要单独修复，不能修改评分期望掩盖。
- 阶段 1 三轮基线、目标数值校准与阶段 2–9 均未验收；本次不追加付费轮次。
