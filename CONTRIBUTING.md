# 贡献指南

## 开始前

1. 从最新目标分支创建功能分支。
2. 不提交 `.env`、密钥、数据库转储、日志、截图、模型缓存或诊断输出。
3. 保持公司作用域、只读经营库、证据引用和任务恢复边界不变，除非变更明确要求调整这些契约。

## 本地环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Set-Location backend
pip install -e ".[dev]"
Copy-Item .env.example .env
```

前端：

```powershell
Set-Location frontend
npm ci
```

## 提交前验证

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m ruff format --check app tests
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m pytest tests -q -m "not e2e and not slow"

Set-Location ..\frontend
npm test
npm run build

Set-Location ..
docker compose config --quiet
git diff --check
```

只运行目标测试时，请在提交说明中列出未运行的测试。Mock、进程内 `.run()` 和配置校验不能描述为真实 Worker E2E。

## 变更要求

- API 或持久化契约变化应同时更新 Schema、迁移、测试和 README 中受影响的公开说明。
- 权限必须由后端确定；客户端和 LLM 不能扩大公司、文档或 Tool 范围。
- 事实、假设、建议和限制保持分离；新增生成路径必须经过确定性校验。
- 新依赖必须解决现有能力无法覆盖的问题，并说明运行与维护成本。
- 不提交学习笔记、个人资料、录屏、临时评测输出或已废弃实现的归档副本。

## Pull Request 说明

至少写明：

- 解决的问题和行为变化。
- 影响的入口、状态、权限、事务和失败路径。
- 执行的命令与结果。
- 测试证明了什么、没有证明什么。
- 是否需要迁移、配置变更或回滚步骤。
