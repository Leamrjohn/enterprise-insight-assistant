# 贡献指南

> 项目规则见 [AGENTS.md](AGENTS.md)，设计和验收以 [主路线图](docs/plans/single_node_production_style_ai_application_roadmap.md) 为准；本文只说明协作流程。

## 开始前

1. 从最新目标分支创建功能分支。
2. 不提交 `.env`、密钥、数据库转储、日志、截图、模型缓存或诊断输出。
3. 保持公司作用域、只读经营库、证据引用和任务恢复边界不变，除非变更明确要求调整这些契约。

## 本地环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Set-Location backend
python -m pip install -r requirements/base.txt -e ".[dev]"
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
..\.venv\Scripts\python.exe -m ruff format --check app tests scripts
..\.venv\Scripts\python.exe -m ruff check app tests scripts
..\.venv\Scripts\python.exe -m pytest tests -q -m "not e2e and not slow"

Set-Location ..\frontend
npm test
npm run build

Set-Location ..
docker compose config --quiet
git diff --check
```

只运行目标测试时，请在提交说明中列出未运行的测试。Mock、进程内 `.run()` 和配置校验不能描述为真实 Worker E2E。

## CI 与提交前检查

### 测试分层

测试配置在 `backend/pyproject.toml`，不是独立 pytest.ini。以下命令从 backend 目录运行，均需已配置的隔离测试环境：

| 范围 | 命令 | 证明边界 |
|---|---|---|
| 单元与脚本 | `python -m pytest tests/unit tests/scripts -m "not e2e and not slow" -q` | 部分 fixture 仍连接 PostgreSQL；目录名不保证纯单元隔离 |
| 集成 | `python -m pytest tests/integration -m "not e2e and not slow" -q` | 不包含真实 Worker、LocalStack 链路或慢模型测试 |
| E2E 选测检查 | `python -m pytest tests/integration -m e2e --collect-only -q` | 只核对收集范围，不执行、不证明端到端通过 |

真实 Worker 和对象存储测试还分别要求 `RUN_REAL_CELERY_E2E=1`、`RUN_LOCAL_OBJECT_STORAGE_E2E=1` 及各自依赖服务；仅指定 `-m e2e` 不会开启这些开关。附件入口继续冻结，本段不授权开启业务上传。`slow` 测试需要按具体场景准备真实模型等依赖。

严格 marker 检查已启用，未知标记会导致收集失败，不应通过关闭严格检查来规避。skip、deselect、仅收集都不算测试通过。此前证据中的 `-k "not business_gold"` 是本地验证的额外排除，不是当前 CI 命令；两者不能报告为相同覆盖。仓库 Gold 文件的结构/指纹测试也不等于仓库外密封留出评测。

### 提交钩子

安装后端 `.[dev]` 后，在仓库根目录启用提交钩子：

```powershell
$env:PYTHONUTF8 = "1"
python -m pre_commit install
python -m pre_commit run --all-files
```

Windows 中文路径下先启用 UTF-8，避免生成的 Git hook 中解释器路径编码错误。

钩子使用与 CI 相同的 Ruff 0.16.1，检查 `backend/app`、`backend/tests`、`backend/scripts`。默认不自动修复或格式化；需要调整时，先对选定文件运行 `python -m ruff format <文件>`，检查差异后重新验证。存量问题仍是失败，不通过跳过钩子或忽略检查来宣称验收。

`.github/workflows/ci.yml` 在 PR、push 和手动触发时分别运行 Ruff 检查、格式检查、Pyright、单元/脚本测试、集成测试、前端测试与构建、Compose 配置检查。后端使用 Python 3.12、独立 PostgreSQL/Redis 服务；复用初始化 SQL，并分别以迁移角色建表、应用角色运行测试。测试任务生成的 JUnit 保存 14 天。

单元/脚本和集成任务使用 `-m "not e2e and not slow"`；被排除和条件跳过的场景不算通过。后端 CI 按 `backend/requirements/ci-linux-py312.lock` 校验哈希安装，再离线安装项目并检查声明与实装依赖一致性；运行日志记录实装版本。工作流存在不代表已在 GitHub 通过，也不自动启用分支保护；实际 PR run、必需检查、故障演练和学习验收仍需单独验证。

## CI 依赖锁生成与验证

在独立 Linux x86_64 / Python 3.12 环境中，从 `backend` 目录运行；不要用已有 Windows 虚拟环境的 `pip freeze` 代替解析。工具安装也应在专用环境内进行：

```sh
python -m pip install pip==26.2.2 pip-tools==7.6.2
python -m piptools compile --all-build-deps --only-build-deps --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host --quiet --output-file /tmp/ci-build.txt pyproject.toml
python -m piptools compile --extra dev --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host --quiet --output-file requirements/ci-linux-py312.lock pyproject.toml requirements/base.txt /tmp/ci-build.txt
```

构建依赖先单独提取，因为 pip-tools 不支持对多个输入同时使用 `--all-build-deps`。生成结果只面向该 CI 环境，不包含模型 Worker 的 `ml.txt`，也不代表 Windows 锁定安装已验证。修改依赖声明时须重新生成并检查锁差异；生成失败不得手填版本或哈希。

在新的 Linux/Python 3.12 虚拟环境，从仓库根目录验证：

```sh
python -m pip install --require-hashes -r backend/requirements/ci-linux-py312.lock
python -m pip install --no-index --no-build-isolation -r backend/requirements/base.txt -e './backend[dev]'
python -m pip check
```

第二步不访问索引，不允许依赖声明需要的新包被在线解析后悄悄绕过锁。然后运行静态检查与独立数据库测试；当前锁的本地验证范围见 `docs/evidence.md`。Python 补丁版本、操作系统镜像与系统工具不由该 Python 锁文件固定。

## 变更要求

### 数据库回滚边界

回退代码不等于可以直接回退数据库。先核对目标 revision、停止相关写入并完成可恢复备份，再在隔离副本验证目标约束与现有数据兼容；只在空库执行 downgrade 不足以证明业务数据可回退。

当前最新迁移 `x1a2b3c4d5e6` 回到 `w0a1b2c3d4e5` 时，旧版本不接受 `conversation_messages.status = 'awaiting_review'`。停止相关写入后，可先检查：

```sql
SELECT count(*) FROM conversation_messages WHERE status = 'awaiting_review';
```

非零时停止回退，保留当前数据库版本；须先确定业务上合法的处置或兼容发布方案。不要为使迁移通过而删除消息、强改成 completed 或移除约束。检查与迁移之间必须维持停止写入，避免检查后又产生不兼容数据。继续回退更早 revision 须逐项审查，不能把这一版本的验证推广到整条迁移链。

### 接口与依赖

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
