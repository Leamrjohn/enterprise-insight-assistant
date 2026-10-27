## 2026-10-27 — 恢复平台数据库容器
- 备份原数据卷后，删除旧空目录，仅重新创建 PostgreSQL 容器，保留原数据卷；未运行迁移。
- 验证：PostgreSQL healthy；数据库与代码迁移版本均为 x1a2b3c4d5e6；Worker 的 SELECT 1 返回 1。
- 未通过：就绪检查 HTTP 503，数据库、Redis、对象存储为 ok，容量信号不可用；该容器已停止。
- 待办：检查健康检查疑似未指定数据库名，导致重复出现 database agent_app does not exist 日志；本次未修改。
## 2026-10-27 — 恢复环境依赖并验收
- 启动现有 capacity-signal、beat、frontend 容器；未重建容器或执行迁移。
- 验证：API /health/ready 与前端代理均 HTTP 200，database/redis/object_storage/task_capacity 均 ok；前端首页 HTTP 200。
- Worker 内 SELECT 1 返回 1；容量信号、Beat、前端及两个 Worker 最近三分钟日志未匹配到错误。
- 边界：本轮验证运行环境与连接，未提交经营问题、未调用模型；此前数据库健康检查库名待办保留。
