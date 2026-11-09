# 冒烟基线 2026-11-09

- Git: `34229790f8485f7e17958409ed3f6d9f357cee18`
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
| data-east-delivered-revenue-2025-08 | 成功 | 未运行 | 未运行 | 17.75 | 6952 | 0.002694 |
| data-east-sales-comparison-repair-v2 | 成功 | 未运行 | 未运行 | 10.15 | 7024 | 0.002756 |
| data-known-region-empty-month-v7 | 成功 | 未运行 | 未运行 | 10.14 | 5661 | 0.002175 |
| knowledge-quality-batch-evidence | 成功 | 未运行 | 未运行 | 24.24 | 6089 | 0.002308 |
| knowledge-margin-two-factors | 成功 | 未运行 | 未运行 | 10.13 | 4931 | 0.001956 |
| knowledge-receivable-risk-boundary | 成功 | 未运行 | 未运行 | 10.14 | 5146 | 0.00211 |
| hybrid-east-delivered-revenue-causality-boundary | 失败 | 未运行 | 未运行 | 16.19 | 9929 | 0.004081 |
| clarification-missing-time-range | 成功 | 未运行 | 未运行 | 6.12 | 5007 | 0.00178 |
| long-document-bad-debt-provision | 成功 | 未运行 | 未运行 | 10.15 | 8315 | 0.002901 |
| long-document-inventory-turnover | 成功 | 未运行 | 未运行 | 10.15 | 8860 | 0.003032 |

- 四类汇总：{'成功': 9, '结果错误': 0, '失败': 1, '无响应': 0}

| 轮次 | 用例 | task_id | 状态/阶段 | 秒数 | tokens | cost | 评分差异/异常类型 |
|---|---|---|---|---|---|---|---|
| 1 | data-east-delivered-revenue-2025-08 | 895 | completed/completed | 17.75 | 6952 | 0.002694 | ; None |
| 1 | data-east-sales-comparison-repair-v2 | 896 | completed/completed | 10.15 | 7024 | 0.002756 | ; None |
| 1 | data-known-region-empty-month-v7 | 897 | partial/completed | 10.14 | 5661 | 0.002175 | ; None |
| 1 | knowledge-quality-batch-evidence | 898 | completed/completed | 24.24 | 6089 | 0.002308 | ; None |
| 1 | knowledge-margin-two-factors | 899 | completed/completed | 10.13 | 4931 | 0.001956 | ; None |
| 1 | knowledge-receivable-risk-boundary | 900 | completed/completed | 10.14 | 5146 | 0.002110 | ; None |
| 1 | hybrid-east-delivered-revenue-causality-boundary | 901 | awaiting_review/awaiting_review | 16.19 | 9929 | 0.004081 | ; None |
| 1 | clarification-missing-time-range | 902 | needs_clarification/completed | 6.12 | 5007 | 0.001780 | ; None |
| 1 | long-document-bad-debt-provision | 903 | completed/completed | 10.15 | 8315 | 0.002901 | ; None |
| 1 | long-document-inventory-turnover | 904 | completed/completed | 10.15 | 8860 | 0.003032 | ; None |

## 执行事件（不含凭据）

- {"event": "identity", "value": {"git": "34229790f8485f7e17958409ed3f6d9f357cee18", "runtime": {"containers": {"agent-api-1": {"source": "0c25621508f5bda888e37512bf6b22d32ea08274ae9a2c67e8cfd8216fda23f0", "model": {"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "workflow_release_version": "v1", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:f8a54d434a5b36b226eac91f618314b0ad91a7a904695fb93765eb64eea69850"}, "agent-worker-1": {"source": "0c25621508f5bda888e37512bf6b22d32ea08274ae9a2c67e8cfd8216fda23f0", "model": {"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "workflow_release_version": "v1", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:0d757d7e90f6a61f58f887ff608bd68c512218f575925dbb4750e35ec5e4c7c2"}, "agent-report-worker-1": {"source": "0c25621508f5bda888e37512bf6b22d32ea08274ae9a2c67e8cfd8216fda23f0", "model": {"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash", "workflow_release_version": "v1", "llm_timeout_seconds": 30, "llm_temperature": 0.2, "llm_max_output_tokens": 1024, "analysis_task_model_max_calls": 8, "analysis_task_model_max_total_tokens": 16000, "analysis_task_model_max_cost": "0.15", "model_price_table_version": "deepseek-v4.1-flash-peak-2026-10-10", "model_price_table": [{"price_id": "deepseek-v4.1-flash-peak-cache-miss", "provider": "deepseek", "model_name": "deepseek-v4-flash", "parameters": {}, "prompt_per_1k": "0.0003", "completion_per_1k": "0.0012"}], "reranker_model": "BAAI/bge-reranker-base", "rag_retrieval_policy": "paragraph_jieba_rrf_rerank_v1", "rag_retrieval_top_k": 10, "rag_rerank_top_k": 3, "endpoint_sha256": "a34e2a4708ed1c61008a151688838dcf1c44d4e7f08054633e72ba7c0b16cfc1", "request_seed": null}, "image": "sha256:cb1dad72ec0835d5bf62a4710f7cb39ef9943fa92ea51b6460ea30aacca021fe"}}, "business_dump_sha256": "2ec89eeb9bad576f352a94b72aa5661527d3d86436df7efc0822f5479e0be0ba", "corpus_version": "1.0+llm", "corpus_seed": 20260718}, "cases_sha256": "d984013f6ca0ad1e94a91dbecacd4af43aaf12494628ed52acfe82eaacd76bd1", "corpus_manifest_sha256": "1307b4f130b70bda39a16f6e2f5e60ba24c18eb8b9fa515ea8254f265d841148", "runner_sha256": "82da8bd8dfc8d00daa56db92734be1666d921c217047bb8f35c61d434c625be9"}}
- {"event": "fixture", "user_id": 282, "company_id": 274, "membership_id": 273}
- {"event": "round", "round": 1, "seconds": 125.25, "tokens": 67914, "cost": 0.025793}
- {"event": "done"}
