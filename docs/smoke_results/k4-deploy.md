# 冒烟基线 2026-11-10

- Git: `88ec222e23668f875825072efbc49a1dfdafbb44`
- 原开发用例期望未修改；oracle_review 尚为 pending，不是独立留出评测。
- 隔离测试租户；经 HTTP 登录、建会话、提问、轮询，评分复用持久化 Observation。
- 每题 180 秒；超时请求取消；费用沿用服务账本单位，未知不计为零。

| 编号 | 问题原文 | 选择理由 | fixture SHA256 |
|---|---|---|---|
| data-east-delivered-revenue-2025-08 | 区域名称为“华东”的2025年8月、状态为 delivered 的订单销售额是多少？ | 已交付销售额正常结果 | 32f449765a4f9e3037f1a5b5a2862d25a16907ef8b8101106dab9bad5c81e05b |
| data-east-sales-comparison-repair-v2 | 比较华东区2025年7月与8月已交付订单销售额。 | 跨月比较与语义投影 | c09d29e0e6e12dfa86c5d59b2d7a11e717c95efbb114698438f8e8f02b562fb4 |
| data-known-region-empty-month-v7 | 华东区2020年3月销售额是多少？ | 已知实体但时间窗口无数据 | c5746e2635b5f51727a0d3b0cd13c8e9a1d46453ed73e4de8f6c813b8740314c |
| knowledge-quality-batch-evidence | 哪些资料支持SUP-003传感器批次异常？ | 纯知识路线的支持证据 | 9918b1b96567d76da47d9939def6c33a0d77daf776208cb389f915b44f6d3592 |
| knowledge-margin-two-factors | 传动控制毛利压力有哪些被资料支持的因素？ | 多因素与禁止单一归因 | 228117a8e924ac27ad97cd20ae716f29c186859c5542c727e1e9316127a997a8 |
| knowledge-receivable-risk-boundary | 哪些资料支持CUST-0280回款风险上升？ | 风险结论的证据边界 | 9918b1b96567d76da47d9939def6c33a0d77daf776208cb389f915b44f6d3592 |
| hybrid-east-delivered-revenue-causality-boundary | 请给出华东区2025年8月状态为 delivered 的订单销售额；并根据资料说明 CUST-0001 合同到期与暂停采购的关系，且明确这些资料是否足以证明其是华东全部销售表现的唯一原因。 | 数据与文档联合归因边界 | c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c |
| clarification-missing-time-range | 华东区销售额是多少？ | 缺时间范围应澄清 | c91c4096840a5f49a7703b530aa5279c7a65c77610b203ab52ee2495f3f967ee |
| long-document-bad-debt-provision | 根据应收风险提示，对华北汽车零部件客户067建议按什么比例计提坏账准备？ | 长文档检索：在多份相近文档中找到正确片段 | 63c43dafd8756e0bf4c945df52c91e0d815be4cbda0fcf74d7f8fd6cfb823bfb |
| long-document-inventory-turnover | 根据库存物流简报，2025年6月电气自动化类的周转天数是多少？ | 长文档检索：在多份相近文档中找到正确片段 | 63c43dafd8756e0bf4c945df52c91e0d815be4cbda0fcf74d7f8fd6cfb823bfb |

| 编号 | 第1次 | 第2次 | 第3次 | 平均秒数 | token合计 | 费用合计 |
|---|---|---|---|---|---|---|
| data-east-delivered-revenue-2025-08 | 成功 | 未运行 | 未运行 | 15.58 | 6966 | 0.002696 |
| data-east-sales-comparison-repair-v2 | 成功 | 未运行 | 未运行 | 10.15 | 7044 | 0.002749 |
| data-known-region-empty-month-v7 | 成功 | 未运行 | 未运行 | 8.13 | 5695 | 0.0022 |
| knowledge-quality-batch-evidence | 成功 | 未运行 | 未运行 | 26.29 | 6102 | 0.002316 |
| knowledge-margin-two-factors | 成功 | 未运行 | 未运行 | 10.16 | 4938 | 0.001971 |
| knowledge-receivable-risk-boundary | 成功 | 未运行 | 未运行 | 10.16 | 5057 | 0.002038 |
| hybrid-east-delivered-revenue-causality-boundary | 失败 | 未运行 | 未运行 | 18.22 | 9854 | 0.004033 |
| clarification-missing-time-range | 成功 | 未运行 | 未运行 | 4.11 | 3143 | 0.001135 |
| long-document-bad-debt-provision | 成功 | 未运行 | 未运行 | 10.21 | 8292 | 0.002884 |
| long-document-inventory-turnover | 成功 | 未运行 | 未运行 | 12.18 | 8867 | 0.003037 |

- 四类汇总：{'成功': 9, '结果错误': 0, '失败': 1, '无响应': 0}

| 轮次 | 用例 | task_id | 状态/阶段 | 秒数 | tokens | cost | 评分差异/异常类型 |
|---|---|---|---|---|---|---|---|
| 1 | data-east-delivered-revenue-2025-08 | 915 | completed/completed | 15.58 | 6966 | 0.002696 | ; None |
| 1 | data-east-sales-comparison-repair-v2 | 916 | completed/completed | 10.15 | 7044 | 0.002749 | ; None |
| 1 | data-known-region-empty-month-v7 | 917 | partial/completed | 8.13 | 5695 | 0.002200 | ; None |
| 1 | knowledge-quality-batch-evidence | 918 | completed/completed | 26.29 | 6102 | 0.002316 | ; None |
| 1 | knowledge-margin-two-factors | 919 | completed/completed | 10.16 | 4938 | 0.001971 | ; None |
| 1 | knowledge-receivable-risk-boundary | 920 | completed/completed | 10.16 | 5057 | 0.002038 | ; None |
| 1 | hybrid-east-delivered-revenue-causality-boundary | 921 | awaiting_review/awaiting_review | 18.22 | 9854 | 0.004033 | ; None |
| 1 | clarification-missing-time-range | 922 | needs_clarification/completed | 4.11 | 3143 | 0.001135 | ; None |
| 1 | long-document-bad-debt-provision | 923 | completed/completed | 10.21 | 8292 | 0.002884 | ; None |
| 1 | long-document-inventory-turnover | 924 | completed/completed | 12.18 | 8867 | 0.003037 | ; None |

## 执行事件（不含凭据）

- {"event": "identity", "value": {"git": "88ec222e23668f875825072efbc49a1dfdafbb44", "runtime": {"containers": {"agent-api-1": {"source": "f38a242f9539f1b6b60b440d0753eff32d851aff9ad3d21b661cbe7959a8c904", "model": {"reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "workflow_release_version": "v1", "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:5a1fdd3fb0b0908620145748618b2af68113e11ef80522810686cffb520141ca"}, "agent-worker-1": {"source": "f38a242f9539f1b6b60b440d0753eff32d851aff9ad3d21b661cbe7959a8c904", "model": {"reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "workflow_release_version": "v1", "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:b3d09de4094f97970778eb91b0f6397e8330e72405bdbdae63d339ffab751274"}, "agent-report-worker-1": {"source": "f38a242f9539f1b6b60b440d0753eff32d851aff9ad3d21b661cbe7959a8c904", "model": {"reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "workflow_release_version": "v1", "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:a991dce5c9222310613d641563e754565748e9770d1d0be7a1a7d82c92638eee"}}, "business_dump_sha256": "2ec89eeb9bad576f352a94b72aa5661527d3d86436df7efc0822f5479e0be0ba", "corpus_version": "1.0+llm", "corpus_seed": 20260718}, "cases_sha256": "d984013f6ca0ad1e94a91dbecacd4af43aaf12494628ed52acfe82eaacd76bd1", "corpus_manifest_sha256": "1307b4f130b70bda39a16f6e2f5e60ba24c18eb8b9fa515ea8254f265d841148", "runner_sha256": "82da8bd8dfc8d00daa56db92734be1666d921c217047bb8f35c61d434c625be9"}}
- {"event": "fixture", "user_id": 284, "company_id": 276, "membership_id": 275}
- {"event": "round", "round": 1, "seconds": 125.29, "tokens": 65958, "cost": 0.025059}
- {"event": "done"}
