# 经营知识库生成语料

本目录由 `backend/scripts/generate_business_data.py` 从固定 seed 的业务数据库生成。不要手工修改 Markdown 或 `manifest.json`；数据库重建后重新运行生成器即可同步刷新。

测试默认使用 `manifest.json` 的场景小语料（通常 1–3 篇），避免每次运行都嵌入全量文档。`full_regression` 仅用于少量独立回归或 E2E。

文档只包含可复算事实、明确的业务背景和结论边界；不包含 `evaluation.scenario_truth` 中的答案键。
