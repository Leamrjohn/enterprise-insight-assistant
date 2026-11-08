# API 和前端实现设计

**状态：** 设计稿，未实现。文中代码是草案。对应总计划工单 B16、B17。

**不变的约束：** 文件和附件上传入口保持冻结，不新增、不放开；客户端不能提交预算、权限或范围；不接受用户原始 SQL。

---

## 1. 现在怎么运行

```text
前端      App.tsx（256 行，页面和组件都在一个文件，很多逻辑写在单行）
          api.ts ApiClient：fetch + Bearer；令牌在 sessionStorage（App.tsx:254）
提问      POST /conversations/{id}/messages → 202 + 任务号
          API 同步写任务和 Outbox，再尝试发布（conversations/api.py:342）
结果      前端定时轮询 GET …/tasks/{task_id}（App.tsx:116）
操作      取消 POST …/cancel；重试 POST …/retry
错误      core/exceptions.py 统一处理（main.py:61-66）
```

**要保留的好设计：**
- 异步模型：202 + 任务号，不让请求等待模型。
- 准入限制：429 和 503 带 `Retry-After`（`api.py:274-285`）。
- 令牌放 `sessionStorage`，关闭页面即失效。
- 重试走新的执行尝试（`retry_conversation_task_service`）。

**存在的问题：**

| 问题 | 依据 | 实际后果 |
|---|---|---|
| 无 API 版本 | 路由直接 `/conversations`（`api/router.py`） | 改接口就可能破坏前端和调用方 |
| 发消息没有幂等键 | `ConversationMessageCreate` 只有 `content`（`schemas.py:28`） | 网络重试或双击可能建两个任务、花两份钱 |
| 轮询固定频率 | `App.tsx:116` | 任务多时压力大；用户看不到中间进度细节 |
| 错误结构不统一 | `detail` 和 `message` 都有（`api.ts:53`） | 前端要兼容多种格式，靠文本映射翻译 |
| 列表无分页 | `/conversations` 返回列表（`api.py:166`） | 数据多了变慢 |
| 前端代码集中 | `App.tsx` | 难改、难测 |
| 只有基础单测 | `DocumentPage.test.tsx`、`api.test.ts` | 核心流程没有端到端测试 |
| 跑开发服务器 | `docker-compose.yml:231` | 不是生产形态 |
| 令牌过期直接掉线 | 无刷新流程 | 分析任务进行中可能要重新登录 |
| 无反馈入口 | | 无法收集“这个回答没帮助” |

---

## 2. API 规范（B16）

### 2.1 版本

```text
新路径   /api/v1/conversations/…
旧路径   保留一个版本周期，响应头 Deprecation，前端切换后删除
健康检查 /health/* 不加版本
```

`api/router.py` 增加前缀。新前端和旧路径并存，切换可以一步步进行。

### 2.2 错误格式

```json
{
  "code": "task_admission_limited",
  "message": "当前任务较多，请稍后再试。",
  "details": [],
  "request_id": "b1f3…",
  "retryable": true
}
```

| 规则 | 说明 |
|---|---|
| `code` | 机器读取，稳定不变，集中在 `core/error_codes.py` |
| `message` | 给用户看的中文；不含内部字段、SQL、堆栈 |
| `retryable` | 前端据此显示“重试”按钮 |
| 状态码 | 400 输入、401 未登录、403 无权限、404、409 状态冲突、422 校验、429、503 |

**前端不再靠文本映射，** 只按 `code` 处理。现有 `_is_audited_analysis_rejection`（`middleware.py:22`）继续工作。

### 2.3 发消息幂等

```text
请求头 Idempotency-Key: <前端生成的 UUID>

处理：
1 查 (company_id, user_id, key) 是否存在
2 存在且内容哈希相同 → 返回原来的任务（200）
3 存在但内容不同 → 409
4 不存在 → 和任务、Outbox 同一事务写入
```

```sql
CREATE TABLE idempotency_keys (
  company_id integer NOT NULL,
  user_id integer NOT NULL,
  key varchar(64) NOT NULL,
  request_hash varchar(64) NOT NULL,
  task_id integer NOT NULL REFERENCES analysis_tasks(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (company_id, user_id, key)
);
-- 开启并强制 RLS；定时清理（默认保留 24 小时）
```

**并发：** 依赖主键冲突判断，冲突的一方读取并返回已有任务。

**重试接口也支持同样的键。** 没带键的旧客户端保持现有行为。

### 2.4 进度推送

**先优化轮询，再考虑 SSE。** 现在的任务常在 10～20 秒完成，轮询足够。

| 阶段 | 做法 |
|---|---|
| 1 | 轮询退避：1s → 2s → 3s → 5s；响应带 `ETag` 或 `updated_at`，无变化返回 304 |
| 2 | `GET /api/v1/conversations/{id}/tasks/{id}/events?after=<sequence>`：从 `workflow_events` 返回白名单事件 |
| 3（可选） | SSE。多 Worker 或长任务才值得。单机 uvicorn 上要测连接数 |

**只暴露白名单阶段：** 排队中、理解问题、查询数据、检索资料、复核、完成。不返回 SQL、工具参数、提示词。

### 2.5 分页和其他

- 列表统一游标分页：`?limit=20&cursor=…`，上限 100。
- OpenAPI 生成的契约文件进版本库，CI 比较破坏性变更；前端类型从中生成，替代手写 `types.ts`。
- 请求体大小上限；消息长度上限（`ConversationMessageCreate.content` 现在只有最小值，`schemas.py:30`，**要加上限**）。
- 响应不返回 `credential_env_var` 和连接配置（安全设计 A11 处理）。`organizations/api.py:57-58` 现在会返回给调用方，开工时确认该接口的可见范围。

---

## 3. 前端（B17）

### 3.1 结构

```text
frontend/src/
    app/            路由、布局、登录状态
    api/            生成的类型、客户端、错误处理
    features/
        assistant/  对话、输入、任务状态
        report/     报告、引用、限制、审核
        documents/  已有文档页（不扩大上传能力）
        sources/    数据源（选择平台登记的连接）
        semantic/   语义层草稿和批准（管理员）
        memory/     记忆查看和复核（管理员）
        account/    成员
        operations/ 运行状态
    components/     通用组件
```

**拆分方式：** 先把 `App.tsx` 现有函数（`LoginScreen`、`ReportView`、`AssistantPage` 等，`App.tsx:21-241`）原样移动，再加路由和测试。先不换 UI。

**依赖：** 路由和数据请求库是否引入要批准。这个规模用少量代码也可行；建议只加 `react-router` 和生成类型的工具，不引入大型状态管理。

### 3.2 任务页状态

| 状态 | 显示 | 可做的操作 |
|---|---|---|
| `queued` | 排队中 | 取消 |
| `running` | 当前阶段 | 取消 |
| `retrying` | 系统正在恢复（不是错误） | 取消 |
| `needs_clarification` | 具体问题 | 直接回答 |
| `awaiting_review` | 等待审核 | 管理员可审核 |
| `partial` | 报告 + **醒目的限制说明** | 重试、反馈 |
| `completed` | 报告 | 反馈、复制 |
| `failed` | 原因 + 是否可重试 | 重试 |
| `cancelled` | 已取消 | 重新提问 |

**`partial` 不能和 `completed` 长得一样：** 否则用户会把不完整结论当完整结论。

### 3.3 报告页

| 区域 | 内容 |
|---|---|
| 摘要 | 数字可点击，跳到来源 |
| 确认事实 | 来自查询，标“数据” |
| 文档发现 | 标“文档”，带引用和限定条件 |
| 原因假设 | 明确标“假设，未证实”，不和事实混在一起 |
| 限制 | 缺什么、下一步 |
| 来源 | 文档名、页码、片段（用户无权限时不显示） |
| 技术详情（管理员） | 任务号、提示词版本、费用 |

**普通用户界面不出现 `chunk_id`。** 代码层再过滤（设计 12）。

**反馈：** “有帮助 / 没帮助 + 原因”，写 `task_feedback` 表。这是真实问题回流的入口（评测设计第 8 节）。

### 3.4 登录和令牌

配合安全设计 A3：

```text
访问令牌  内存或 sessionStorage，短期
刷新令牌  HttpOnly + Secure + SameSite Cookie，JS 读不到
过期      请求返回 401 → 自动刷新一次 → 再失败才跳登录
任务进行中 不丢失对话状态
```

**改用 Cookie 要同时加 CSRF 防护。** 这是一处明确的取舍，开工时一起设计。

### 3.5 生产构建

见工程化设计 4.3：`npm ci` → `npm run build` → nginx。CSP 等安全头放在 nginx。

### 3.6 可访问性和移动端

现有 `mobile-fixes.css` 保留。关键流程要能用键盘操作；状态变化提供文字说明，不只靠颜色。

---

## 4. 一次提问的具体过程

```text
前端  生成 Idempotency-Key，POST /api/v1/conversations/7/messages
API   鉴权 → 限流 → 配额 → 幂等检查 → 写任务和 Outbox → 202 {task_id:1002}
前端  显示“排队中”；轮询 1s
      网络中断 → 用同一个 Key 重发 → 得到同一个任务，不重复计费
      1s  排队中；3s 理解问题；6s 查询数据；10s 复核；11s 完成
前端  渲染报告；partial 时显示限制条
      用户点“没帮助” → POST /tasks/1002/feedback
```

---

## 5. 失败路径

| 场景 | 前端 | API |
|---|---|---|
| 网络中断 | 自动用同一个 Key 重试有限次 | 幂等返回 |
| 401 | 刷新一次，再失败回登录，保留输入内容 | |
| 403 | 提示无权限 | 写审计 |
| 429 | 按 `Retry-After` 显示倒计时 | |
| 503 | 提示暂不可用，可重试 | |
| 轮询失败 | 退避继续，顶部提示连接问题；不把任务显示成失败 | |
| 任务长时间无进度 | 显示“比平时慢”，提供取消 | 告警 |
| 报告结构版本未知 | 显示已知字段和提示 | |
| 同一 Key 不同内容 | 提示重新发送 | 409 |

---

## 6. 配置

| 配置项 | 默认值 |
|---|---|
| `API_V1_PREFIX` | `/api/v1` |
| `API_LEGACY_ROUTES_ENABLED` | `true`，切换后 `false` |
| `IDEMPOTENCY_TTL_HOURS` | 24 |
| `MESSAGE_MAX_CHARS` | 4000（初值，按上下文预算校准） |
| `VITE_API_BASE` | 环境决定 |
| `VITE_POLL_INTERVALS` | 代码常量 |

---

## 7. 落地步骤

**验证命令是计划，尚未运行。** 新前端依赖要批准；Playwright 是新依赖。

| 工单 | 改动 | 验证 | 回滚 |
|---|---|---|---|
| **B16a 错误格式** | `core/error_codes.py`、处理器；前端按 `code` | 所有错误路径返回统一结构；前端测试 | 兼容旧字段 |
| **B16b 幂等键**（**改表**） | 新表、`conversations/service.py`、前端 | 并发相同 Key 只建 1 个任务；不同内容 409 | 不带 Key 时保持旧行为 |
| **B16c 版本前缀** | `api/router.py`、前端 | 新旧路径都可用；E2E 过 | 开关 |
| **B16d 分页和上限** | 列表接口 | 大数据量测试；超长消息 422 | revert |
| **B16e 事件接口** | 白名单事件 | 不含敏感字段（测试）；跨公司 0 | 不启用 |
| **B16f OpenAPI 契约** | 生成文件、CI 比较 | 破坏性变更被 CI 发现 | 改为告警 |
| **B17a 拆前端** | 只移动代码 | 现有测试全过；手工走一遍 | revert |
| **B17b 轮询退避** | `assistant/` | 无变化时请求减少 | revert |
| **B17c 状态和报告** | 第 3.2、3.3 节 | `partial` 明显区分；组件测试 | revert |
| **B17d 反馈**（**改表**） | `task_feedback`、前端 | 记录任务号和原因；跨公司 0 | 隐藏入口 |
| **B17e 生产构建** | Dockerfile、compose | 容器提供静态页；安全头存在 | 回到 vite |
| **B17f 端到端**（**新依赖**） | Playwright，假模型 | 登录 → 提问 → 看报告 → 看引用 | 不进必需检查 |

---

## 8. 怎么确认它真的生效

| 检查 | 通过标准 |
|---|---|
| 双击发送或断网重发 | 只有一个任务，只扣一次费 |
| 所有错误 | 结构相同，前端不依赖文本 |
| `partial` 报告 | 一眼能看出不完整 |
| 令牌过期 | 无感刷新，不丢内容 |
| 无进度变化的轮询 | 返回 304 |
| 普通用户界面 | 没有 `chunk_id`、SQL、内部字段 |
| 改接口破坏兼容 | CI 失败 |
| 上传相关 | 没有新增入口，现有范围不变 |

**仍需开工时确认：** `App.tsx` 当前的完整交互（文件里很多逻辑写在单行，这轮只看了结构）；文档页和上传相关接口的现有范围（`documents/api.py:59`、`:122`），它们属于冻结范围，不在本设计内改动；uvicorn 在单 Worker 下的 SSE 能力。
