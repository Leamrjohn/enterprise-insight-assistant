# 系统提示词（G1）

每个提示词一个文件，登记在 `manifest.json`：`version`（版本）、`file`、`variables`（模板变量）、`sha256`（去掉末尾换行、统一 LF 后的内容哈希）。代码通过 `app/modules/runtime/prompts.py` 的 `get_prompt_registry()` 读取。

**改提示词的步骤：** 改文件 → 升 `version` → 更新 `sha256` → 跑对应评测（录音会失配，需要批准后重录）。只改文件不改清单，Worker 启动就会失败。

**模板变量：** `${name}`，字面的美元符号写 `$$`；缺变量或多变量都会报错。

**还在代码里的：** SQL 生成和 Data 工具提示词按表结构动态拼接，留给上下文引擎（C4）接管。
