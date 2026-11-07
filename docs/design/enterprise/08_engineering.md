# 工程化实现设计

**状态：** 设计稿，未实现。文中配置是草案。对应总计划工单 E1～E12。

**目标：** 代码合并前自动验证；同一提交构建结果一致；发布可回滚；重要决定有记录。

---

## 1. 现在怎么运行

```text
本地开发    分支 work/smoke-baseline → pre-commit 跑 ruff
构建        api.Dockerfile:11 pip install -r requirements/base.txt（版本范围）
部署        scripts/ops/up.ps1、stack.ps1 在本机启动 compose
CI          GitHub Actions：ruff、pyright、单元、集成、前端、compose 配置
```

**CI 的基础其实不错，要保留：** Action 按提交哈希固定（`ci.yml:25`）；依赖锁文件带哈希（`ci.yml:33`）；迁移用 `agent_migrator`，测试用 `agent_app`（`ci.yml:109-120`）；前端用 `npm ci`；有真实 PostgreSQL 和 Redis。

**真正的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| **工作分支从未进 CI** | 远程只有 `main` 等 4 个分支，没有 `work/smoke-baseline`；比 `main` 多 255 个提交（最早 2026-07-05） | 这些提交的“测试通过”都只是本地结果 |
| 镜像不用锁文件 | `api.Dockerfile:11`；`base.txt` 20 行只有 4 个精确版本 | 同一提交两次构建可能不同；CI 测的和运行的可能不是同一套依赖 |
| 基础镜像是浮动标签 | `python:3.12-slim`、`redis:7`、`node:22-alpine` | 悄悄变化 |
| 前端声明写 `latest` | `package.json` | 有 `package-lock.json` 兜底，但一次 `npm install` 就可能大版本跳变 |
| 前端跑开发服务器 | `docker-compose.yml:231` | 不是生产形态 |
| 没有安全扫描 | `ci.yml` | 依赖漏洞和提交的密钥不会被发现 |
| 没有架构规则 | | `core` 依赖 `modules`；`runtime` 和 `workflow` 互相依赖 |
| 评测不在 CI | 录音含业务数据且被忽略（`replay.py:7`） | 提示词改坏了 CI 也发现不了 |
| 迁移只测升级 | `ci.yml:112` | 69 个 `downgrade` 是否可用未验证 |
| 无发布流程 | 没有镜像版本、CHANGELOG | 出问题回不去 |
| 文件过大 | `nodes.py` 982 行、`tasks.py` 865 行、`execution.py` 836 行 | 难改、难审 |

---

## 2. 分支和合并（E1）

### 2.1 把 255 个提交安全合入

**这是所有工程化工作的前提，也是对外动作，需要批准。**

| 步 | 做什么 | 为什么 |
|---|---|---|
| 1 | **决定仓库可见性。** 现在是公开仓库，默认分支是 `feature/api-contracts` | 推送就等于公开全部 255 个提交和文档。建议先改私有，并把默认分支改成 `main` |
| 2 | 用 gitleaks 扫描 `main..HEAD` 的**全部历史** | 推送前必须确认没有密钥；只扫当前文件不够。公开过的内容即使删除也可能已被缓存 |
| 2b | 仓库保持公开时，先修 A11，再推送安全设计文档 | 不要公开未修复问题的细节 |
| 3 | 处理未提交文件：`AGENTS.md`、`docs/session_00-03_…` | 由用户决定是否提交 |
| 4 | 推送 `work/smoke-baseline`，开 PR | 不强推，不改历史 |
| 5 | 看 CI，按失败修复（每类问题一个提交） | 可能暴露很多积压问题，预留时间 |
| 6 | **合并提交**进 `main`，不压缩 | 保留可追溯的历史 |
| 7 | 打标签 `baseline-2026-11` | 回滚基准 |

**如果扫描发现了密钥：** 停下，轮换该密钥，再决定是否改写历史（改写历史必须另行批准）。

### 2.2 之后的日常规则

```text
main 受保护：只能通过 PR 合并；必需检查全部通过
工单分支：ticket/<工单号>-<简述>
每工单一个 PR，不超过 10 个文件、400 行
提交信息继续用一句话
```

**单人开发也走 PR：** 主要是让 CI 成为不可跳过的门禁，并让你在 PR 上验收。

---

## 3. CI 流水线（E5、E6、E7、E10）

```text
PR 触发（快，目标 15 分钟内）
├ static       ruff、ruff format、pyright
├ architecture import-linter
├ config       配置清单和 .env.example 一致
├ secrets      gitleaks
├ deps         pip-audit、npm audit
├ unit         tests/unit tests/scripts
├ integration  tests/integration（真实 PG、Redis）
├ migrations   upgrade → downgrade -1 → upgrade；alembic check
├ frontend     npm ci、test、build
├ eval-replay  路由、SQL、Knowledge、记忆回放，低于基线就失败
└ compose      docker compose config

合并到 main 后
├ image-build  构建镜像，标记提交哈希，生成 SBOM，trivy 扫描
└ e2e-local    无模型端到端（假模型）

人工或定时（有费用，要批准）
└ smoke-paid   真实模型冒烟
```

| 新增任务 | 怎么做 | 失败时 |
|---|---|---|
| `architecture` | 第 5 节规则 | 阻断 |
| `config` | `python -m app.core.config.catalog --check` | 阻断 |
| `secrets` | gitleaks，配置允许测试用占位值 | 阻断 |
| `deps` | `pip-audit -r …lock`；`npm audit --audit-level=high` | 高危阻断；有理由的例外写入清单并带到期日 |
| `migrations` | 空库升级、回退一步、再升级；`alembic check` 确认模型和迁移一致 | 阻断 |
| `eval-replay` | 见 3.1 | 阻断 |
| `image-build` | `docker buildx`；`trivy image --severity HIGH,CRITICAL` | 高危阻断 |

### 3.1 把评测放进 CI

**难点：** 现有录音含业务数据，在被忽略的 `evaluation-runs/` 目录（`replay.py:7`）。

**方案：** CI 只用**合成语料**的录音，放到 `backend/tests/fixtures/cassettes/`，提交前用 gitleaks 和敏感扫描检查。现在的语料和题目本身是合成数据【记录】，这条开工时要逐一确认。

```text
1 提示词、配置档、切分或路由变化
2 回放找不到录音 → 直接失败（replay.py:60 已有这种行为）
3 开发者获批后重新录制（有费用）→ 提交录音和新基线
4 CI 比较新指标和基线
```

**基线文件：**

```json
{
  "planner_route": {"correct": 43, "total": 48, "min_correct": 43},
  "sql_result": {"correct": 22, "total": 24, "min_correct": 21, "wrong_number_allowed": 0},
  "knowledge": {"correct": 49, "total": 57, "min_correct": 49},
  "memory": {"correct": 8, "total": 8, "min_correct": 8}
}
```

**改基线要在 PR 中写明理由，并由用户批准。** 这和“不能为通过测试改期望”的规则一致。CI 用 CODEOWNERS 保护这个文件。

### 3.2 测试分层

| 层 | 目录 | 依赖 | 触发 | 目标时长 |
|---|---|---|---|---|
| 单元 | `tests/unit` | 无 | 每次 PR | 3 分钟 |
| 契约 | `tests/unit/contracts`（新） | 无 | 每次 PR | 1 分钟 |
| 集成 | `tests/integration` | PG、Redis | 每次 PR | 15 分钟 |
| 回放评测 | `scripts/evaluation` | 录音 | 每次 PR | 5 分钟 |
| 端到端（假模型） | `tests/e2e`（新） | 整套 compose | 合并后 | 15 分钟 |
| 冒烟（真实模型） | `run_smoke_tests.py` | 真实模型 | 人工 | 3 分钟，有费用 |
| 演练 | `scripts/ops/drills` | 整套 compose | 每季度或大改 | 按项 |

**覆盖率：** 先测基线，**只要求不下降**，不定绝对数字，防止为了数字写无意义的测试。

**被跳过的测试：** `skipif`、`e2e`、`slow` 的测试要逐一归入某一层，并在某个触发时机真的运行。不能永远不跑。

---

## 4. 可复现构建（E2、E3）

### 4.1 Python 依赖

现有 `pip-compile` 已生成带哈希的 `ci-linux-py312.lock`（2961 行）。扩展它，不换工具：

```text
requirements/
    base.txt            直接依赖（人编辑）
    ml.txt
    base.lock           pip-compile --generate-hashes
    worker.lock         base + ml
    ci.lock             base + dev
```

```dockerfile
FROM python:3.12-slim@sha256:<固定摘要> AS build
COPY requirements/ requirements/
RUN pip install --require-hashes -r requirements/base.lock
…
USER app
```

**要去掉 `pip install --upgrade pip`：** 否则每次构建 pip 版本都可能变。

**锁文件要在 Linux 上生成：** Windows 上解析出的依赖不同。提供 `scripts/ops/update-locks.ps1`，在容器里运行。

**CPU 和 ML 依赖：** `evaluation-full.Dockerfile` 用了单独的 PyTorch 下载地址，这部分要单独锁定和验证。

**更新依赖：** 开 Dependabot（只开 PR，不自动合并），或者每月更新一次。**新增和升级依赖都需要批准。**

### 4.2 基础镜像和服务镜像

| 现在 | 目标 |
|---|---|
| `python:3.12-slim` | 带摘要固定 |
| `redis:7` | `redis:7.x.y@sha256:…` |
| `node:22-alpine`（跑开发服务器） | 多阶段构建 → `nginx`（固定摘要）提供静态文件 |
| 其他已精确到版本 | 补摘要 |

### 4.3 前端

- `package.json` 把 `latest` 改成当前 lock 文件里的实际版本。
- 新增 `frontend/Dockerfile`：`npm ci` → `npm run build` → nginx。
- 增加 Playwright（**新依赖，需批准**），端到端测试：登录 → 提问 → 看报告 → 看引用。
- 开发时仍可用 `vite`，由 compose override 切换。

### 4.4 模型文件

嵌入和重排模型、tiktoken 词表都不在运行时下载。构建时放进镜像或固定目录，**版本和哈希写进清单**。

---

## 5. 架构规则（E4）

```toml
# backend/.importlinter（新依赖，需批准）
[importlinter]
root_package = app

[importlinter:contract:layers]
name = 分层依赖方向
type = layers
layers =
    app.modules.workflow
    app.modules.analysis | app.modules.knowledge | app.modules.reporting
    app.modules.runtime
    app.modules.documents | app.modules.organizations | app.modules.identity
    app.core

[importlinter:contract:control-session]
name = 只有控制面可以使用控制会话
type = forbidden
```

`layers` 这段是草案，要按实际依赖调整。**存量违规先放进忽略清单，只禁止新增，再逐步清零。** 已知要处理的：

| 违规 | 解决方式 |
|---|---|
| `core/gateway/*` → `modules/runtime` | G2 把网关移到 `runtime/models`，`core` 不再有业务依赖 |
| `core/middleware.py` → `observability` | 改为在 `main.py` 组装时注入 |
| `runtime` ↔ `workflow` | `runtime` 定义接口，`workflow` 实现（审计写入、任务读取） |

### 大文件拆分（B1）

**只移动，不改行为。** 每次移动一个节点，每次一个提交。

```text
workflow/orchestration/nodes/
    planner.py  data.py  knowledge.py  reviewer.py  terminal.py  common.py
workflow/tasks/
    entry.py  execute.py  publish.py  lease.py
```

**验证：** 全部测试不变；冒烟不变；`git log --follow` 能追踪。

---

## 6. 迁移规则（E7）

**发布时用“扩展—迁移—收缩”：**

```text
第 1 版  只新增字段或表（新旧代码都能运行）
第 2 版  代码写新字段，回填，切换读取
第 3 版  确认稳定后删除旧字段（删除要批准）
```

| 规则 | 检查方式 |
|---|---|
| 每个迁移都能升级和回退，或标注不可逆 | CI 往返测试；标注列表 |
| 新增非空字段必须有默认值或分步 | 人工评审 |
| 大表加索引用 `CONCURRENTLY` | 人工评审 |
| 执行前备份 | `up.ps1` 流程里检查 |
| 不用数据卷重建来“解决”问题 | 项目硬规则 |

---

## 7. 发布和回滚（E8）

```text
版本号    语义版本；每次发布写 CHANGELOG
镜像      ghcr.io/<仓库>/api:<提交哈希>，另打版本标签
部署清单  deployments/<版本>.env：各镜像的摘要、迁移版本、配置哈希
部署      backup → migrate → 启动新容器 → 健康检查 → 冒烟（可选）→ 记录
回滚      使用上一个清单的镜像；数据库保持（因为是扩展式迁移）
```

```powershell
scripts/ops/deploy.ps1   -Release 1.4.0
scripts/ops/rollback.ps1 -To 1.3.2
```

| 场景 | 处理 |
|---|---|
| 健康检查失败 | 自动回滚容器 |
| 新版本行为变差 | `rollback.ps1`；任务可用 `workflow_version_override` 单独回滚 |
| 迁移失败 | 迁移在事务内回滚；旧容器继续运行 |
| 进行中的任务 | Worker 优雅退出，任务由租约恢复；快照保证行为一致 |

**当前是单机：** 无法零停机，发布有短暂中断。零停机属于上线级。

---

## 8. 协作规范（E9、E11、E12）

| 文件 | 内容 |
|---|---|
| `docs/adr/NNNN-标题.md` | 背景、选项、决定、后果。第一批：模块化单体、记忆分表、RLS 控制角色 |
| `.github/pull_request_template.md` | 工单号、改动、验证层、改前改后结果、没验证到什么 |
| `.github/CODEOWNERS` | 基线文件、迁移、权限、SQL 校验、工具目录要用户批准 |
| `CHANGELOG.md` | 每次发布 |
| `docs/README.md` | 总计划是唯一入口；旧计划标记“历史参考” |
| `AGENTS.md` | 更新当前阶段目标，指向总计划（要用户确认） |

**清理（各一个小工单）：** 未使用的 `core/error_handling.py`【记录】；`tests/modules` 只剩缓存文件的旧目录；`docs/plans/` 的归档位置。

**运维脚本跨平台：** 现有都是 PowerShell。PowerShell 7 也能在 Linux 上跑，所以**保留并修正路径和 docker 调用**，比重写便宜；在 CI 的 Ubuntu 上执行一次，确认可用。

---

## 9. 工具配置汇总

| 工具 | 用途 | 状态 |
|---|---|---|
| ruff、pyright、pre-commit、pip-compile | 已有 | 保留 |
| gitleaks | 查密钥 | **新增，需批准** |
| pip-audit、npm audit | 依赖漏洞 | **新增，需批准** |
| trivy、SBOM（syft） | 镜像扫描 | **新增，需批准** |
| import-linter | 架构规则 | **新增，需批准** |
| Playwright | 前端端到端 | **新增，需批准** |

---

## 10. 落地步骤

**验证命令是计划，尚未运行。**

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **E1 分支集成**（**需批准推送**） | 第 2.1 节 | gitleaks 0 命中；同一提交 CI 全绿；`main` 已合并 | 标签回退 |
| **E2 后端锁定** | `*.lock`、Dockerfile | 同一提交两次构建 `pip freeze` 完全一致；冒烟不变 | revert |
| **E3 版本固定** | compose、`package.json`、前端镜像 | 无浮动标签（脚本检查） | revert |
| **E4 架构规则** | `.importlinter`、CI | 故意新增反向依赖时 CI 失败 | 忽略清单 |
| **E5 分层门禁** | CI、标记、覆盖率基线 | 被跳过的测试都有运行时机 | revert |
| **E6 安全扫描** | CI 任务 | 故意提交假密钥时失败 | 改为只告警 |
| **E7 迁移门禁** | CI 往返、规则文档 | 不可回退的迁移被发现 | 改为只告警 |
| **E8 发布回滚** | `deploy.ps1`、`rollback.ps1`、CHANGELOG | 演练：发布 → 回滚 → 冒烟 | 手工启动 |
| **E9 协作规范** | ADR、模板、CODEOWNERS | 分支保护生效 | 无 |
| **E10 评测门禁** | 录音、基线、CI | 故意改坏提示词时失败 | 改为只告警 |
| **E11 文档整理** | README、总计划入口 | 链接检查通过 | 无 |
| **E12 脚本跨平台** | `scripts/ops/` | Ubuntu 上能运行 | 无 |

**建议顺序：** E1 → E6 → E2 → E3 → E5 → E7 → E4 → E10 → 其余。E1 必须最先，否则其他 CI 改动都不会运行。

---

## 11. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 提交假密钥 | CI 失败 |
| 新增反向依赖 | CI 失败 |
| 改提示词不升版本 | CI 失败 |
| 把 Knowledge 改坏 | 回放评测失败 |
| 写不能回退的迁移 | CI 失败（除非已标注） |
| 同一提交构建两次 | 依赖完全相同 |
| 发布后回滚 | 回到上一版本，冒烟通过 |
| 不走 PR 直接推 `main` | 被拒绝 |

**仍需开工时确认：** GitHub Actions 对私有仓库的额度；`e2e` 整套 compose 在 CI 上的资源是否够；分支保护在当前 GitHub 计划下是否可用；CI 里运行需要 ML 模型的评测是否太慢（不够时只回放不需要嵌入的部分，其余放定时任务）。
