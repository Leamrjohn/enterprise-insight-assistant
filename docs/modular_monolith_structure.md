# 模块化单体目录约束

## 目的

项目按业务领域组织，而不是按技术层平铺。一次变更应能在一个领域目录内找到其 HTTP 入口、契约、持久化和业务规则；跨领域调用必须通过明确的函数与数据契约，而不能依赖目录习惯。

## 顶层边界

```text
app/
  modules/       # 领域代码；每个领域拥有自己的 api、models、schemas、repository、service、agent、tool 或 task
  core/          # 跨领域技术能力：配置、日志、异常、模型网关、Celery 应用
  db/            # SQLAlchemy Base、连接和租户会话机制
  api/router.py  # 只组合各领域路由，不包含业务逻辑
  main.py        # 应用启动和基础设施装配
```

`modules/` 的初始领域为：`identity`、`organizations`、`conversations`、`documents`、`input_artifacts`、`analysis`、`knowledge`、`workflow`、`reporting`、`reviews`、`memory`、`runtime`、`observability` 与 `evaluation`。

## 不变量

- ORM 模型移动后，Alembic 仍显式导入全部模型；迁移历史和数据库表名不因目录调整而改变。
- `api/router.py` 仍是唯一 HTTP 组合点；领域 API 不相互 include。
- Celery 仍只从明确的任务入口加载任务，稳定任务名与 beat 配置随模块路径同步更新。
- 分析主链、RLS、公司范围、租约、检查点、Outbox 与确定性发布门禁保持不变。
- 测试目录按领域镜像生产目录；导入旧平铺路径视为迁移未完成，而不是保留兼容层。

## 本次迁移的验收

1. `app.api`、`app.models`、`app.repositories`、`app.schemas`、`app.services`、`app.agents`、`app.tasks` 和 `app.tools` 不再存放领域实现；
2. 全部生产代码、测试、Alembic 装配和 Celery 配置引用新路径；
3. Python 编译、测试收集和当前可运行的回归测试通过；
4. 此次不改表结构、HTTP 路径、任务状态或任务语义。
