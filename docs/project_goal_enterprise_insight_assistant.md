# 固化项目目标：Enterprise Insight Assistant

适用范围：`C:\Users\qyf21\Desktop\1\Agent项目学习` 及其同一项目的后续会话。

## 产品定义

项目是一个独立 Web 应用，不是浏览器插件。名称为 **Enterprise Insight Assistant（企业经营洞察助手）**。

它面向企业经营人员：用户提出经营问题，系统只从已授权的只读经营数据库和该用户上传的文档知识库取证，输出可追溯的结构化经营分析报告。报告必须说明：发生了什么、数据确认了什么、可能原因、建议行动、相应的数据或文档证据，以及证据不足或失败的限制。项目不承诺模型能自动找到唯一真实根因。

重点放到后端代码教学中，前端以及web应用方面可以放到后期

## MVP 范围

第一版支持四类固定场景：区域销售下降、毛利下降、客诉上升、应收风险。先以“华东区 2026 年 6 月销售额为何较 5 月下降”为端到端示范场景；其他场景复用同一架构逐步扩展。

用户不能输入原始 SQL。第一版不提供任意自然语言 SQL、无限制 Agent、多 Agent 自由辩论、OCR/视觉、写入经营库、自动执行经营动作、跨租户访问、实时 BI 或浏览器插件。

## 前端页面

1. 登录页：JWT 登录，用户只访问自己的文档、任务和报告。
2. 分析工作台：输入问题；选择场景、区域、当前月、对比月和可选文档；创建任务；显示 queued、查经营数据、检索文档、生成报告、completed/partial/failed 等状态。
3. 分析报告页：固定展示结论摘要、已确认事实、可能原因（假设）、建议行动、数据证据、文档引用和限制。
4. 文档知识库页：上传、处理状态、文档与引用分块查看、删除自己的文档。
5. 历史报告页：查看自己的任务、状态、报告、错误原因，支持重新发起。

## 报告可信度契约

- **事实**：必须直接来自受控经营数据，包含查询或指标依据。
- **假设**：必须有当前用户授权文档的引用支撑，且显式标注为未证实因果。
- **建议**：必须指回至少一条事实或假设，包含优先级和行动内容。
- **限制**：数据、文档或模型异常时，不能伪装为完成；明确返回 partial 或 failed，并说明补充资料或排查方向。
- 数字必须能回溯到 SQL 查询结果；文档引用必须属于当前用户并确实存在。

## 后端实现边界

数据流：Web 前端 -> `POST /analysis-runs` -> 创建持久化任务 -> Celery Worker -> Planner -> Data Agent（受控查询模板/受控 SQL + 只读经营库）和 Knowledge Agent（当前用户文档 RAG）-> Reviewer/Report -> 持久化结构化报告 -> 前端轮询展示。

- API 只做请求校验、鉴权、创建/查询/取消任务；不在 HTTP 请求内执行长分析。
- Celery 负责异步投递和执行，任务数据库记录才是状态事实来源；任务创建必须提交后再 delay，使 Worker 的独立 Session 可见。
- Planner 仅把问题映射到固定场景与数据/文档计划，不生成最终结论。
- Data Agent 只能经受控 SQL Tool 查询只读经营数据。
- Knowledge Agent 只能检索当前用户有权限的文档，不能访问经营库。
- Reviewer/Report 负责合成事实、假设、建议、限制，并校验数字和引用，不得编造。

建议接口：`POST /analysis-runs`、`GET /analysis-runs`、`GET /analysis-runs/{id}`、`POST /analysis-runs/{id}/cancel`、`POST /documents/upload`、`GET /documents`、`GET /documents/{id}/chunks`。

最终结果应持久化结构化字段：status、scenario、confirmed_facts、hypotheses（含 document_chunk_ids）、recommendations（含 priority/basis）、limitations、数据证据和文档引用；不能只保存一个 RAG answer 字符串。

## 当前代码判断与后续优先级

现有仓库已有受控 SQL Tool、RAG Tool、Planner/Data/Knowledge/Reviewer Agent、LangGraph workflow、分析任务与 Celery 骨架。当前 `/tasks` Worker 仍是单独 RAG 流程，尚未真正调用数据加文档的工作流；前端尚不存在；最终结构化报告尚未完整持久化与展示。这些是项目主线，不应通过增加更多 Agent 来绕开。

## MVP 验收

1. 用户上传至少两份业务文档，并能发起一条区域销售下降问题。
2. Worker 以独立只读连接取得可复现经营数据。
3. 报告含至少一条可验证事实、一条有真实文档引用的原因假设和一条有依据的建议。
4. 文档不足返回 partial，不编造原因；SQL/模型失败返回 failed，并展示失败阶段。
5. 第二用户无法读取第一用户的文档、任务或报告。
6. 前端完整展示进度、报告、数据证据、文档证据和限制。
7. 每项完成以解释、修改、验证、排错四项证据衡量；仓库已有代码不自动代表学习者已掌握或项目已完成。
