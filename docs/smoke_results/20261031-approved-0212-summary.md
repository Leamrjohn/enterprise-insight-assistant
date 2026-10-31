# 获授权完整单轮冒烟结果

- 用户授权最多 8 题、$0.20、30 分钟；预检于 2026-10-31 02:12:41 EDT 开始，13 个项目服务运行、API readiness=True，工作区干净。运行代码为 `9a6bf69`，身份校验通过。
- 命令：`.\.venv\Scripts\python.exe backend/scripts/evaluation/run_smoke_tests.py --run-id 20261031-approved-0212`，退出码 0，收到 done；只运行一轮，没有自动续跑。
- 实跑 8 题，任务 177–184：成功 7、失败 1、结果错误 0、无响应 0；成功率 87.5%。混合题 183 awaiting_review，未发布，按原分类记失败；184 needs_clarification 符合用例期望。
- 整轮 73.1 秒，56,470 token，估算费用 $0.021357。数据库只读核对 42 条模型/本地资源账本，全部 settled、费用非空，token 与费用合计均与执行器一致；未核对供应商账单。
- 复核请求 19 pending，publication=awaiting_human_review/causal_hypothesis_requires_human_review，仅存在 report_draft、无 report。未取消或自动审批；任务 176 的既有批准不适用于本任务。
- 对照上轮：原执行器在第 7 题待复核时停止并出现终态评分 ValueError；本轮第 7 题保持待复核、无该评分异常，并继续第 8 题。两个运行的版本不同，只用于行为对照，不能拼成同一版本三轮基线。
- 原始结果见同名 `.md` 与 `artifacts/smoke/20261031-approved-0212.json`，包含代码、模型参数、数据与脚本指纹；退出码 0 仅表示执行完整，不代表全部用例成功。
- 仍缺同一冻结版本的三轮基线、目标数值校准及阶段验收；没有运行额外轮次，未修改评分期望或发布门禁。
