## 2026-10-27 — 恢复平台数据库容器
- 备份原数据卷后，删除旧空目录，仅重新创建 PostgreSQL 容器，保留原数据卷；未运行迁移。
- 验证：PostgreSQL healthy；数据库与代码迁移版本均为 x1a2b3c4d5e6；Worker 的 SELECT 1 返回 1。
- 未通过：就绪检查 HTTP 503，数据库、Redis、对象存储为 ok，容量信号不可用；该容器已停止。
- 待办：检查健康检查疑似未指定数据库名，导致重复出现 database agent_app does not exist 日志；本次未修改。
