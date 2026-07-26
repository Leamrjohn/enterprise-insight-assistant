# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

企业经营人员使用经营助手提出受限范围内的经营问题；公司管理员维护公司数据源、契约快照与成员权限。

## Product Purpose

Enterprise Insight Assistant 从当前公司获授权的只读经营数据和限定文档范围取证，返回可追溯的结构化经营分析。用户能发起并跟踪异步分析；管理员能安全维护其公司的运行数据边界。

## Positioning

系统将公司、数据源、当前契约快照和可访问文档冻结在分析任务中，使数值、引用、推断与限制能够被回溯，而非提供无边界聊天。

## Operating Context

桌面浏览器中的登录后工作台。后端以 `X-API-Key` 鉴权；分析通过会话创建、异步任务投递与任务状态轮询完成。当前公司上下文由后端从认证用户的成员关系推导，客户端不能选择公司 ID。

## Capabilities and Constraints

- 经营助手选择一个本公司数据源与可访问文档范围，创建会话并发送消息。
- 分析消息的结果状态为 queued、running、completed、partial、failed 或 cancelled。
- 数据源与快照操作、成员查看与修改仅对 owner/admin 可见；分析仅允许 owner/admin/analyst。
- 数据库凭据只以环境变量名展示和提交，界面不得显示密码值。
- 现有后端尚无用户名密码或 JWT 登录接口；前端使用 API Key 建立会话。
- 现有成员 API 返回成员 ID、用户 ID、角色、状态与创建时间；并未返回其他用户姓名。

## Brand Commitments

用户提供的参考图锁定了登录后入口的明亮留白、浅蓝雾化背景与大字号品牌感。产品名称固定为“企业经营洞察助手”；不复制 DeepSeek 名称、标识或文案。

## Evidence on Hand

后端 API、Pydantic 契约和领域模型位于 `backend/app/api/`、`backend/app/schemas/` 与 `backend/app/models/`。参考图位于用户提供的本地剪贴板图片。当前仓库没有前端工程或真实品牌资产。

## Product Principles

1. 证据范围在发起分析前明确可见。
2. 权限决定可见操作，界面不伪装为权限来源。
3. 异步状态与错误必须可理解、可恢复。
4. 配置与凭据引用分离，避免秘密进入浏览器。

## Accessibility & Inclusion

键盘可达、清晰焦点、中文优先文案、可读的错误恢复说明，以及对减少动态效果偏好的尊重。
