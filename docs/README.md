# 文档索引

## 当前入口（每次只读当前工单）

| 顺序 | 文档 | 回答什么 |
|---|---|---|
| 1 | [协作规则](../AGENTS.md) | 范围、授权、禁止事项与验收流程 |
| 2 | [完整改造计划](design/complete_plan_2026-11-07.md) | 唯一的执行计划：终点、每段做到什么程度、每个工单怎么验收；只读当前段 |
| 3 | 当前工单所在模块的设计（`design/enterprise/`） | 代码位置和草案；只读和工单有关的段落 |
| 4 | [工作日志](worklog.md) | 本次做了什么、实际验证结果与遗留问题 |

`roadmap/` 下的旧计划（阶段 0～9）已被完整改造计划取代，仅作历史参考。

## 目录

| 目录 | 内容 |
|---|---|
| `roadmap/` | 当前执行计划：00 总览、01 阶段 0～2、02 阶段 3～5、03 阶段 6～9 |
| `history/plans/` | 历史计划、设计范围路线图和架构需求，仅在用户点名时阅读 |
| `architecture/` | 目录结构、已确认的目标设计契约 |
| `design/` | 每个模块的生产级设计稿（按 12 问模板，见 [design/README.md](design/README.md)） |
| `operations/` | 单机运行、故障恢复、备份恢复手册 |
| `evaluation/` | 评测前预测模板等评测方法文档 |
| `audits/` | 带日期的代码审计与外部评审材料（快照，不代表当前状态） |
| `history/evidence.md` | 已冻结的历史证据，不再追加 |
| `worklog.md` | 当前工作记录，每个工单最多 5 行 |

## 全部文档

| 文档 | 用途 |
|---|---|
| [history/plans/improvement_and_learning_plan.md](history/plans/improvement_and_learning_plan.md) | 历史改进与学习计划，已由 00～03 计划替代 |
| [history/plans/single_node_production_style_ai_application_roadmap.md](history/plans/single_node_production_style_ai_application_roadmap.md) | 最终设计范围与验收门禁（查询用） |
| [history/plans/agent_architecture_refactor_requirements.md](history/plans/agent_architecture_refactor_requirements.md) | 架构重构需求与上线蓝图 |
| [history/plans/history/agent_core_first_execution_plan.md](history/plans/history/agent_core_first_execution_plan.md) | 已被取代的“核心优先”计划 |
| [architecture/modular_monolith_structure.md](architecture/modular_monolith_structure.md) | 目录结构与依赖规则 |
| [architecture/confirmed_production_design.md](architecture/confirmed_production_design.md) | 已确认的目标设计契约 |
| [design/README.md](design/README.md) | 模块设计稿模板 |
| [operations/single_node_runbook.md](operations/single_node_runbook.md) | 启动、任务检查、队列、备份与恢复 |
| [evaluation/baseline_prediction_template.md](evaluation/baseline_prediction_template.md) | 评测前预测模板 |
| [audits/project_core_audit_20260915.md](audits/project_core_audit_20260915.md) | 2026-09-15 代码审计快照 |
| [audits/for_external_review.md](audits/for_external_review.md) | 外部评审材料 |

根目录：[README](../README.md)（总览与启动）、[PRODUCT](../PRODUCT.md)（产品边界）、[AGENTS](../AGENTS.md)（协作规则）、[CONTRIBUTING](../CONTRIBUTING.md)、[SECURITY](../SECURITY.md)、[DESIGN](../DESIGN.md)（前端设计系统）。演示语料在 [`data/business_knowledge_base/`](../data/business_knowledge_base/README.md)。

## 规则

- 规则冲突时按 AGENTS.md 优先级处理；当前代码与测试决定实现事实。
- 审计与评审材料是带日期的快照，不自动适用于之后的提交。
- 新记录只写入 `worklog.md`；`history/evidence.md` 冻结为历史记录，不再追加。
