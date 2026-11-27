# 文档索引

## 当前入口（每次只读当前工单）

| 顺序 | 文档 | 回答什么 |
|---|---|---|
| 1 | [协作规则](../AGENTS.md) | 范围、授权、禁止事项与验收流程 |
| 2 | [完整改造计划](plan/complete_plan_2026-11-07.md) | 唯一的执行计划：终点、每段做到什么程度、每个工单怎么验收；只读当前段 |
| 3 | 当前工单所在模块的设计（`design/enterprise/`） | 代码位置和草案；只读和工单有关的段落 |
| 4 | [状态记录](STATUS.md)、[工作日志](worklog.md) | 做到哪了、每个工单做了什么和验证结果 |

## 目录

```text
docs/
  README.md          本索引
  STATUS.md          进度，每步一行
  worklog.md         工作日志，每个工单最多 5 行
  plan/              计划：完整改造计划、改造与学习路线、教学计划、面试标准
  design/
    enterprise/      15 个模块的实现设计（00 任务全过程 ～ 14 API 和前端）
    adr/             选型决策记录（引入还是自建）
  evaluation/        评测用的题目选择（development_case_selection.json，冒烟和评测脚本会读它）
  operations/        运行手册、告警手册
  audits/            计划审核记录
  smoke_results/     每次部署后的冒烟记录（run_smoke_tests.py 写到这里）
  learning/          学习材料：R3 前代码讲解、函数索引、R3 工具调用链、运行路线图
  history/           冻结的历史：evidence.md（旧证据）、archive_summary（已删除旧文档的摘要和找回方法）
```

## 找文件

| 想找 | 去哪里 |
|---|---|
| 现在该做哪个工单、怎么验收 | [plan/complete_plan_2026-11-07.md](plan/complete_plan_2026-11-07.md) 第 5 节 |
| 工单分工（训练 / 共建 / 代做） | [plan/build_and_learn_route_2026-11-07.md](plan/build_and_learn_route_2026-11-07.md) 第 6 节 |
| 放手阶梯、毕业考核 | [plan/teaching_plan_2026-11-05.md](plan/teaching_plan_2026-11-05.md) 第 3、8 节 |
| 某个模块的代码位置和设计草案 | `design/enterprise/` 对应编号的文件 |
| 为什么选这个组件 | `design/adr/` |
| 某次部署后冒烟的结果 | `smoke_results/<工单>-deploy-r<轮次>.md` |
| 出故障先做什么 | [operations/alert_runbook.md](operations/alert_runbook.md)、[operations/single_node_runbook.md](operations/single_node_runbook.md) |
| 读懂 R3 之前的代码 | [learning/pre_r3_runtime_guide.md](learning/pre_r3_runtime_guide.md)、[learning/pre_r3_function_index.md](learning/pre_r3_function_index.md) |
| 已删除的旧计划和旧调查 | [history/archive_summary_2026-11-27.md](history/archive_summary_2026-11-27.md) |

根目录：[README](../README.md)（总览与启动）、[PRODUCT](../PRODUCT.md)（产品边界）、[AGENTS](../AGENTS.md)（协作规则）、[CONTRIBUTING](../CONTRIBUTING.md)、[SECURITY](../SECURITY.md)、[DESIGN](../DESIGN.md)（前端设计系统）。演示语料在 [`data/business_knowledge_base/`](../data/business_knowledge_base/README.md)。

## 规则

- 规则冲突时按 AGENTS.md 优先级处理；当前代码与测试决定实现事实。
- 新记录只写入 `STATUS.md` 和 `worklog.md`；`history/` 下的文件冻结，不再追加。
- 新增文档放进上面对应的目录；不要在 `docs/` 根目录放新文件。
