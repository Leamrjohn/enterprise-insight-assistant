# 告警处理手册

每条告警一节，小节名和 `ops/observability/alerts.yml` 里的 `runbook:` 一致。
每节写 4 项：现象、影响、第一步、确认恢复。

## worker-down
- 现象：Worker 心跳超过 2 分钟没更新，或者心跳指标消失。
- 影响：新任务没人处理，用户看到任务一直在排队。
- 第一步：运行 `scripts/ops/status.ps1`，看 `agent-worker-1` 日志的最后 40 行。
- 确认恢复：Grafana 上 Worker 心跳回到 60 秒以内，告警自动消失。

## beat-stalled
- 现象：Beat 心跳超过 2 分钟没更新，或者 Beat 心跳指标消失。
- 影响：定时任务停止，包括扫描过期任务，以及未来的整理数据库、知识库等操作。
- 第一步：看 `agent-beat-1` 日志的最后 40 行。
- 确认恢复：beat心跳正常，相关任务会被触发并执行

## queue-backlog
- 现象：outbox出现长达5分钟未处理的投递任务
- 影响：用户的请求卡在outbox投递，无法被认领处理
- 第一步：运行 `scripts/ops/inspect-queue.ps1`。
- 确认恢复：outbox上没有5分钟仍未投递的任务

## tasks-stranded
- 现象：有任务处于 retrying（等待重试）状态，但没有任何执行在跑，并且已经超过规定时间；这种情况持续了 10 分钟。
- 影响：卡死不处理会导致用户的任务一直卡死，用户无法及时查看结果
- 第一步：运行 `scripts/ops/scan-orphaned-tasks.ps1`。
- 确认恢复：任务恢复正常，被新的worker认领并执行

## exporter-down
- 现象：Prometheus 抓不到导出器（`up` 为 0），或者导出器查库失败（`agent_exporter_up` 为 0）。
- 影响：监控拿不到数据，其他规则该响的时候不响；WorkerDown 反而可能误触发（它用了 `absent()`）。业务本身不受影响。
- 第一步：看 `agent-metrics-exporter-1` 日志的最后 40 行，检查数据库连接。和 worker-down 同时响时，先处理这一条。
- 确认恢复：导出器正常，可以正常导出数据

## unknown-cost-spike
- 现象：1小时内出现5条以上的未知账单
- 影响：无法统计账单情况，以及影响项目优化
- 第一步：查最近 1 小时的模型调用超时和租约过期。
- 确认恢复：近 1 小时新增的 unknown 账单回到 5 条以内，告警自动消失。
