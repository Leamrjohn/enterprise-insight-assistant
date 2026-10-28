# 文档索引

## 当前入口（每次只读当前工单）

| 顺序 | 文档 | 回答什么 |
|---|---|---|
| 1 | [协作规则](../AGENTS.md) | 范围、授权、禁止事项与验收流程 |
| 2 | [计划总览](roadmap/00_overview.md) | 当前执行顺序与阶段门槛；每次读第 1～3 节 |
| 3 | [阶段 0～2](roadmap/01_stages_0-2.md) | 当前阶段工单，只读正在执行的一项 |
| 4 | [工作日志](worklog.md) | 本次做了什么、实际验证结果与遗留问题 |

后续工单：[阶段 3～5](roadmap/02_stages_3-5.md)、[阶段 6～9](roadmap/03_stages_6-9.md)。未进入相应阶段时无需阅读。

## 目录

| 目录 | 内容 |
|---|---|
| `roadmap/` | 当前执行计划：00 总览、01 阶段 0～2、02 阶段 3～5、03 阶段 6～9 |
| `plans/` | 历史计划、设计范围路线图和架构需求，仅在用户点名时阅读 |
| `architecture/` | 目录结构、已确认的目标设计契约 |
| `design/` | 每个模块的生产级设计稿（按 12 问模板，见 [design/README.md](design/README.md)） |
| `operations/` | 单机运行、故障恢复、备份恢复手册 |
| `evaluation/` | 评测前预测模板等评测方法文档 |
| `audits/` | 带日期的代码审计与外部评审材料（快照，不代表当前状态） |
| `evidence.md` | 已冻结的历史证据，不再追加 |
| `worklog.md` | 当前工作记录，每个工单最多 5 行 |

## 全部文档

| 文档 | 用途 |
|---|---|
| [plans/improvement_and_learning_plan.md](plans/improvement_and_learning_plan.md) | 历史改进与学习计划，已由 00～03 计划替代 |
| [plans/single_node_production_style_ai_application_roadmap.md](plans/single_node_production_style_ai_application_roadmap.md) | 最终设计范围与验收门禁（查询用） |
| [plans/agent_architecture_refactor_requirements.md](plans/agent_architecture_refactor_requirements.md) | 架构重构需求与上线蓝图 |
| [plans/history/agent_core_first_execution_plan.md](plans/history/agent_core_first_execution_plan.md) | 已被取代的“核心优先”计划 |
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
- 新记录只写入 `worklog.md`；`evidence.md` 冻结为历史记录，不再追加。
