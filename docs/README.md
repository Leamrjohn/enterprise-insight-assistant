# 文档索引

## 先读

| 顺序 | 文档 | 回答什么 |
|---|---|---|
| 1 | [改进与学习计划](plans/improvement_and_learning_plan.md) | **当前执行计划**：每个模块改成什么样、按什么顺序、怎么教与学 |
| 2 | [目录结构与模块边界](architecture/modular_monolith_structure.md) | 文件在哪里、模块之间怎么调用 |
| 3 | [证据记录](evidence.md) | 做过什么、验证了什么、哪些未证明（唯一的证据台账） |

## 目录

| 目录 | 内容 |
|---|---|
| `plans/` | 当前计划、最终设计范围路线图、架构重构需求；`plans/history/` 存放被取代的计划 |
| `architecture/` | 目录结构、已确认的目标设计契约 |
| `design/` | 每个模块的生产级设计稿（按 12 问模板，见 [design/README.md](design/README.md)） |
| `operations/` | 单机运行、故障恢复、备份恢复手册 |
| `evaluation/` | 评测前预测模板等评测方法文档 |
| `audits/` | 带日期的代码审计与外部评审材料（快照，不代表当前状态） |
| `evidence.md` | 证据台账，只追加不改写历史 |

## 全部文档

| 文档 | 用途 |
|---|---|
| [plans/improvement_and_learning_plan.md](plans/improvement_and_learning_plan.md) | 当前执行计划（2026-10-19 起） |
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
- 证据只写入 `evidence.md`，不另建台账。
