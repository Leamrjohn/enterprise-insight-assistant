import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, ApiError, applyForMembership, bootstrapOwner, login, reapplyForMembership } from "./api";
import type { AssistantDataSource, CompanyInvitation, CompanyMember, Conversation, ConversationMessage, CreatedCompanyInvitation, CurrentUser, DataSource, DocumentChunk, DocumentItem, MembershipApplication, Report, Snapshot, Task, TaskStatus } from "./types";

type Page = "assistant" | "documents" | "sources" | "account";
const TOKEN_KEY = "enterprise-insight.access-token";
const terminal = new Set<TaskStatus>(["completed", "partial", "failed", "cancelled", "needs_clarification"]);

function toChineseError(error: unknown) {
  return error instanceof Error ? error.message : "操作失败，请稍后重试。";
}

function formatDate(value?: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function statusLabel(status: string) {
  return ({ queued: "等待执行", running: "正在分析", retrying: "正在重试", completed: "已完成", partial: "部分完成", failed: "处理失败", cancelled: "已取消", needs_clarification: "请补充信息", ready: "可用", pending: "等待处理", processing: "正在处理", discovery_failed: "发现失败", approved: "已启用", disabled: "已禁用", rejected: "已拒绝" } as Record<string, string>)[status] ?? status;
}

function LoginScreen({ onLoggedIn }: { onLoggedIn: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register" | "bootstrap" | "reapply">("login");
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true); setError(""); setNotice("");
    try {
      if (mode === "login") {
        const result = await login(username, password);
        onLoggedIn(result.access_token);
      } else if (mode === "register") {
        await applyForMembership({ name, username, password, invitation_code: invitationCode });
        setNotice("申请已提交，等待公司管理员审核通过后即可登录。");
        setPassword("");
        setInvitationCode("");
      } else if (mode === "bootstrap") {
        const result = await bootstrapOwner({ name, company_name: companyName, username, password });
        onLoggedIn(result.access_token);
      } else {
        await reapplyForMembership({ username, password, invitation_code: invitationCode });
        setNotice("申请已重新提交，等待公司管理员审核通过后即可登录。");
        setPassword("");
        setInvitationCode("");
      }
    }
    catch (reason) { setError(toChineseError(reason)); }
    finally { setSubmitting(false); }
  }

  function switchMode(nextMode: "login" | "register" | "bootstrap" | "reapply") {
    setMode(nextMode); setError(""); setNotice("");
  }

  return <main className="login-shell">
    <section className="login-brand"><span className="brand-mark" aria-hidden="true">EI</span><span>企业经营洞察助手</span></section>
    <div className="login-layout">
      <section className="login-copy"><p className="kicker">可信经营分析</p><h1>让每一个经营问题，<br />回到可验证的证据。</h1><p>连接当前公司的只读数据源与授权文档，在事实、推断、建议和限制之间保持清晰边界。</p></section>
      <form className="login-card" onSubmit={submit}>
        <div><p className="kicker">安全访问</p><h2>{mode === "login" ? "登录工作台" : mode === "bootstrap" ? "创建首个公司" : mode === "reapply" ? "重新提交申请" : "申请加入公司"}</h2><p className="muted">{mode === "login" ? "请输入公司账户的用户名和密码。" : mode === "bootstrap" ? "仅在平台尚未创建任何公司时可用；创建后将以所有者身份直接进入工作台。" : mode === "reapply" ? "仅适用于已被拒绝的原申请；请使用原公司的有效邀请码。" : "使用管理员提供的邀请码提交申请；审核通过后才能登录工作台。"}</p></div>
        {(mode === "register" || mode === "bootstrap") && <label>姓名<input autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 张三" required minLength={1} maxLength={255} /></label>}
        {mode === "bootstrap" && <label>公司名称<input autoComplete="organization" value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="例如 华东商贸" required minLength={1} maxLength={255} /></label>}
        <label>用户名<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="例如 zhangsan" required minLength={3} /></label>
        <label>密码<input type="password" autoComplete={mode === "login" || mode === "reapply" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位" required minLength={8} /></label>
        {(mode === "register" || mode === "reapply") && <label>邀请码<input value={invitationCode} onChange={(event) => setInvitationCode(event.target.value)} placeholder="请向公司管理员获取" required minLength={16} /></label>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <button className="primary-button" disabled={submitting}>{submitting ? "正在提交…" : mode === "login" ? "登录" : mode === "bootstrap" ? "创建公司并进入工作台" : mode === "reapply" ? "重新提交申请" : "提交申请"}</button>
        {mode === "login" ? <div className="login-actions"><button type="button" className="text-button login-switch" onClick={() => switchMode("register")}>没有账户？申请加入公司</button><button type="button" className="text-button login-switch" onClick={() => switchMode("bootstrap")}>创建首个公司</button></div> : <div className="login-actions"><button type="button" className="text-button login-switch" onClick={() => switchMode("login")}>已有账户？返回登录</button>{mode === "register" && <button type="button" className="text-button login-switch" onClick={() => switchMode("reapply")}>申请被拒？重新提交</button>}</div>}
      </form>
    </div>
  </main>;
}

function ReportView({ report, task }: { report: Report | null; task: Task | null }) {
  if (!task) return <section className="report-placeholder"><p className="kicker">结构化输出</p><h3>结果将在这里呈现</h3><p>每次分析会分开呈现确认事实、可能原因、建议行动和证据限制。</p></section>;
  if (!terminal.has(task.status)) return <section className="report-placeholder"><span className="loading-line" /><p className="kicker">{statusLabel(task.status)}</p><h3>正在整理证据</h3><p>系统正依照当前数据源、契约快照和文档范围执行分析。</p></section>;
  if ((task.status === "failed" || task.status === "cancelled") && !report) return <section className="report-placeholder error-state"><p className="kicker">{statusLabel(task.status)}</p><h3>{task.error_message || "本次分析没有生成报告"}</h3><p>请检查数据源快照、文档范围或稍后重新发起分析。</p></section>;
  if (!report) return <section className="report-placeholder"><p className="kicker">{statusLabel(task.status)}</p><h3>{task.result_summary || "分析已结束"}</h3><p>后端尚未返回可展示的结构化报告。</p></section>;
  const groups: Array<[string, string, Array<{ statement?: string; action?: string; rationale?: string; support_level?: string; priority?: string }> | undefined]> = [
    ["已确认事实", "facts", report.confirmed_facts], ["可能原因", "hypotheses", report.hypotheses], ["建议行动", "recommendations", report.recommendations],
  ];
  return <section className="report"><header><div><p className="kicker">{task.status === "partial" ? "部分完成" : "已完成"}</p><h3>经营分析结果</h3></div><span className={`status status-${task.status}`}>{statusLabel(task.status)}</span></header>
    <p className="summary">{report.executive_summary || task.result_summary}</p>
    {groups.map(([title, key, items]) => items?.length ? <section className="report-group" key={key}><h4>{title}</h4><ol>{items.map((item, index) => <li key={`${key}-${index}`}><strong>{item.statement || item.action}</strong>{item.rationale && <span>{item.rationale}</span>}{(item.support_level || item.priority) && <em>{item.support_level ? `支持度：${item.support_level}` : `优先级：${item.priority}`}</em>}</li>)}</ol></section> : null)}
    {report.data_evidence?.length ? <section className="report-group"><h4>数据证据</h4><div className="evidence-list">{report.data_evidence.map((evidence) => <article className="data-evidence" key={evidence.evidence_id}><strong>{evidence.purpose}</strong><small>证据编号：{evidence.evidence_id}</small>{evidence.columns.length && evidence.rows.length ? <div className="evidence-table-wrap"><table><thead><tr>{evidence.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{evidence.rows.map((row, rowIndex) => <tr key={rowIndex}>{evidence.columns.map((column, columnIndex) => <td key={`${column}-${columnIndex}`}>{String(row[columnIndex] ?? "—")}</td>)}</tr>)}</tbody></table></div> : <p>本项证据未返回可展示的数据行。</p>}</article>)}</div></section> : null}
    {report.document_citations?.length ? <section className="report-group"><h4>文档引用</h4><div className="citation-list">{report.document_citations.map((citation) => <article className="citation" key={citation.chunk_id}><div><strong>文档 #{citation.document_id ?? "—"} · 分块 #{citation.chunk_id}</strong>{citation.score !== null && <small>相关度：{citation.score.toFixed(3)}</small>}</div><p>{citation.excerpt}</p></article>)}</div></section> : null}
    {report.limitations?.length ? <section className="report-group limitation"><h4>资料限制</h4><ul>{report.limitations.map((item, index) => <li key={index}>{typeof item === "string" ? item : item.message || item.statement || "资料不足"}</li>)}</ul></section> : null}
  </section>;
}

function AssistantPage({ api, sources, documents, conversations, refreshConversations }: { api: ApiClient; sources: AssistantDataSource[]; documents: DocumentItem[]; conversations: Conversation[]; refreshConversations: () => Promise<void> }) {
  const readySources = useMemo(() => sources.filter((source) => source.status === "ready" && source.active_schema_snapshot_id !== null), [sources]);
  const [sourceId, setSourceId] = useState<number | null>(readySources[0]?.id ?? null);
  const [documentIds, setDocumentIds] = useState<number[]>(documents.filter((document) => document.status === "completed").map((document) => document.id));
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  const selectedSource = sources.find((source) => source.id === sourceId) ?? null;
  useEffect(() => { if (!conversation && (!selectedSource || selectedSource.status !== "ready" || selectedSource.active_schema_snapshot_id === null)) setSourceId(readySources[0]?.id ?? null); }, [conversation, readySources, selectedSource]);
  const loadConversation = useCallback(async (item: Conversation) => { setDraft(false); setConversation(item); setTask(null); setError(""); setSourceId(item.data_source_id); try { const loadedMessages = await api.messages(item.id); setMessages(loadedMessages); const latestTaskId = [...loadedMessages].reverse().find((message) => message.analysis_task_id)?.analysis_task_id; if (latestTaskId) setTask(await api.task(item.id, latestTaskId)); } catch (reason) { setError(toChineseError(reason)); } }, [api]);
  useEffect(() => { if (!draft && !conversation && conversations[0]) void loadConversation(conversations[0]); }, [conversation, conversations, draft, loadConversation]);
  useEffect(() => { if (!task || !conversation || terminal.has(task.status)) return; const timer = window.setInterval(async () => { try { const latest = await api.task(conversation.id, task.id); setTask(latest); if (terminal.has(latest.status)) setMessages(await api.messages(conversation.id)); } catch (reason) { setError(toChineseError(reason)); window.clearInterval(timer); } }, 1800); return () => window.clearInterval(timer); }, [api, conversation, task]);

  async function send(event: FormEvent) {
    event.preventDefault(); if (!question.trim() || !sourceId) return;
    setSending(true); setError("");
    try {
      let current = conversation;
      if (!current || current.data_source_id !== sourceId) { current = await api.createConversation(sourceId, question.trim().slice(0, 36)); setDraft(false); setConversation(current); await refreshConversations(); }
      const accepted = await api.sendMessage(current.id, question.trim(), documentIds); setQuestion(""); setTask({ id: accepted.task_id, status: "queued", stage: "queued", error_message: null, result_summary: null, report: null, result_data: null }); setMessages(await api.messages(current.id));
    } catch (reason) { setError(toChineseError(reason)); }
    finally { setSending(false); }
  }

  return <div className="assistant-layout"><aside className="conversation-rail"><div className="rail-header"><span>分析会话</span><button onClick={() => { setDraft(true); setConversation(null); setMessages([]); setTask(null); }}>新建</button></div><div className="conversation-list">{conversations.map((item) => <button key={item.id} className={item.id === conversation?.id ? "conversation active" : "conversation"} onClick={() => void loadConversation(item)}>{item.title || "未命名经营分析"}<small>{formatDate(item.updated_at)}</small></button>)}</div></aside>
    <main className="assistant-main"><header className="assistant-header"><div><p className="kicker">经营助手</p><h2>{conversation?.title || "开始一项经营分析"}</h2></div>{task && !terminal.has(task.status) && <button className="quiet-button" onClick={() => conversation && void api.cancelTask(conversation.id, task.id).then(setTask).catch((reason) => setError(toChineseError(reason)))}>取消分析</button>}{task && (task.status === "failed" || task.status === "cancelled") && <button className="quiet-button" onClick={() => conversation && void api.retryTask(conversation.id, task.id).then(async (accepted) => { setTask(await api.task(conversation.id, accepted.task_id)); setMessages(await api.messages(conversation.id)); }).catch((reason) => setError(toChineseError(reason)))}>重新发起</button>}</header>
      <div className="message-list">{messages.map((message) => <article key={message.id} className={`message ${message.role}`}><span>{message.role === "user" ? "你" : "系统"}</span><p>{message.content || statusLabel(message.status)}</p></article>)}</div>
      <ReportView task={task} report={task?.report ?? (task?.result_data?.report as Report | undefined) ?? null} />
      <form className="composer" onSubmit={send}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：华东区 6 月销售额较 5 月下降，哪些数据事实与文档资料能够说明情况？" aria-label="经营问题" /><div className="composer-bottom"><span>{selectedSource ? `数据源：${selectedSource.name}` : "请先选择一个可运行的数据源"}</span><button className="primary-button" disabled={sending || !sourceId}>{sending ? "正在提交…" : "发起分析"}</button></div></form>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </main>
    <aside className="evidence-inspector"><p className="kicker">本次分析范围</p><h3>证据边界</h3><label>经营数据源<select value={sourceId ?? ""} onChange={(event) => { setSourceId(Number(event.target.value)); setConversation(null); setTask(null); }}><option value="" disabled>选择数据源</option>{sources.map((source) => <option key={source.id} value={source.id} disabled={source.status !== "ready" || source.active_schema_snapshot_id === null}>{source.name}{source.status !== "ready" || source.active_schema_snapshot_id === null ? "（暂不可运行）" : ""}</option>)}</select></label>{!readySources.length && <p className="inline-error">当前没有可运行的数据源。请由管理员发现并启用契约快照后再发起分析。</p>}<div className="scope-item"><span>运行契约快照</span><strong>{selectedSource?.active_schema_snapshot_id ? `版本 #${selectedSource.active_schema_snapshot_id}` : "尚未选择"}</strong><small>当前任务将使用此版本限制可查询的表、字段和关联。</small></div><fieldset><legend>文档检索范围</legend>{documents.length ? documents.map((document) => <label className="check-row" key={document.id}><input type="checkbox" checked={documentIds.includes(document.id)} disabled={document.status !== "completed"} onChange={() => setDocumentIds((selected) => selected.includes(document.id) ? selected.filter((id) => id !== document.id) : [...selected, document.id])} /><span>{document.name}<small>{document.status === "completed" ? "可检索" : statusLabel(document.status)}</small></span></label>) : <p className="muted">当前没有可选择的已处理文档。</p>}</fieldset></aside>
  </div>;
}

function DocumentPage({ api, documents, refreshDocuments }: { api: ApiClient; documents: DocumentItem[]; refreshDocuments: () => Promise<void> }) {
  const [selectedId, setSelectedId] = useState<number | null>(null); const [chunks, setChunks] = useState<DocumentChunk[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const selected = documents.find((document) => document.id === selectedId) ?? null;
  const hasPendingDocuments = documents.some((document) => document.status === "pending" || document.status === "processing");
  useEffect(() => { if (!hasPendingDocuments) return; const timer = window.setInterval(() => { void refreshDocuments().catch((reason) => setError(toChineseError(reason))); }, 2500); return () => window.clearInterval(timer); }, [hasPendingDocuments, refreshDocuments]);
  useEffect(() => { if (!selected || selected.status !== "completed") { setChunks([]); return; } void api.documentChunks(selected.id).then(setChunks).catch((reason) => setError(toChineseError(reason))); }, [api, selected?.id, selected?.status]);
  function selectDocument(document: DocumentItem) { setSelectedId(document.id); setChunks([]); setError(""); }
  async function upload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const file = new FormData(event.currentTarget).get("file"); if (!(file instanceof File) || file.size === 0) { setError("请选择一个非空文件。"); return; } setBusy(true); setError(""); try { await api.uploadDocument(file); event.currentTarget.reset(); await refreshDocuments(); } catch (reason) { setError(toChineseError(reason)); } finally { setBusy(false); } }
  async function remove(document: DocumentItem) { if (!window.confirm(`确定删除“${document.name}”吗？删除后该文档不能再作为分析证据。`)) return; setBusy(true); setError(""); try { await api.deleteDocument(document.id); if (selectedId === document.id) { setSelectedId(null); setChunks([]); } await refreshDocuments(); } catch (reason) { setError(toChineseError(reason)); } finally { setBusy(false); } }
  return <main className="page-content"><header className="page-header"><div><p className="kicker">公司资料</p><h2>文档知识库</h2><p>上传后的文档会异步解析为可引用的分块；只有处理完成的文档才能用于经营分析。</p></div></header>{error && <p className="inline-error" role="alert">{error}</p>}<section className="document-upload"><form onSubmit={upload}><label>选择文档<input name="file" type="file" required disabled={busy} /></label><p className="muted">系统会验证文件类型、大小和同公司重复内容。</p><button className="primary-button" disabled={busy}>{busy ? "正在上传…" : "上传并解析"}</button></form></section><div className="document-layout"><section className="document-list"><h3>当前公司文档</h3>{documents.length ? documents.map((document) => <article key={document.id} className={selected?.id === document.id ? "document-row active" : "document-row"}><button onClick={() => void selectDocument(document)}><strong>{document.name}</strong><small>{document.file_type || document.source} · {formatDate(document.created_at)}</small><span className={`status status-${document.status}`}>{statusLabel(document.status)}</span></button>{document.error_message && <p className="inline-error">{document.error_message}</p>}<button className="text-button reject-button" disabled={busy} onClick={() => void remove(document)}>删除</button></article>) : <div className="empty-state">尚未上传文档。上传销售周报、客户反馈或会议纪要后，经营分析才能引用其中的资料。</div>}</section><section className="chunk-detail">{selected ? <><header><div><p className="kicker">文档分块</p><h3>{selected.name}</h3><p>{chunks.length} 个可引用分块</p></div><span className={`status status-${selected.status}`}>{statusLabel(selected.status)}</span></header>{selected.status !== "completed" ? <div className="empty-state">该文档仍在处理，页面会自动刷新状态。</div> : chunks.length ? <div className="chunk-list">{chunks.map((chunk) => <article key={chunk.id}><strong>分块 #{chunk.chunk_index + 1}</strong><small>{chunk.token_count} tokens{chunk.page_number ? ` · 第 ${chunk.page_number} 页` : ""}</small><p>{chunk.content}</p></article>)}</div> : <div className="empty-state">文档已完成，但当前没有可展示的分块。</div>}</> : <div className="empty-state">选择一个已处理文档以查看其可引用分块。</div>}</section></div></main>;
}

function SourcePage({ api, sources, refresh, canManage }: { api: ApiClient; sources: DataSource[]; refresh: () => Promise<void>; canManage: boolean }) {
  const [selected, setSelected] = useState<DataSource | null>(sources[0] ?? null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", host: "", port: "5432", database: "", user: "", schema: "public", credential_env_var: "" });
  useEffect(() => { if (selected) setSelected(sources.find((source) => source.id === selected.id) ?? sources[0] ?? null); }, [sources]);

  const loadSnapshots = useCallback(async (source: DataSource) => { setSelected(source); setError(""); try { setSnapshots(await api.snapshots(source.id)); } catch (reason) { setError(toChineseError(reason)); } }, [api]);
  useEffect(() => { if (selected) void loadSnapshots(selected); }, [selected?.id]);
  async function discover() { if (!selected) return; setBusy(true); try { await api.discover(selected.id); await refresh(); await loadSnapshots(selected); } catch (reason) { setError(toChineseError(reason)); } finally { setBusy(false); } }
  async function activate(snapshot: Snapshot) { if (!selected) return; setBusy(true); try { await api.activateSnapshot(selected.id, snapshot.id); await refresh(); await loadSnapshots(selected); } catch (reason) { setError(toChineseError(reason)); } finally { setBusy(false); } }
  async function create(event: FormEvent) { event.preventDefault(); setBusy(true); try { await api.createDataSource({ name: form.name, credential_env_var: form.credential_env_var, connection: { host: form.host, port: Number(form.port), database: form.database, user: form.user, schema: form.schema } }); setShowCreate(false); setForm({ name: "", host: "", port: "5432", database: "", user: "", schema: "public", credential_env_var: "" }); await refresh(); } catch (reason) { setError(toChineseError(reason)); } finally { setBusy(false); } }
  return <main className="page-content"><header className="page-header"><div><p className="kicker">公司配置</p><h2>数据源管理</h2><p>数据库密码由部署环境管理；此处只配置连接信息与凭据环境变量名称。</p></div>{canManage && <button className="primary-button" onClick={() => setShowCreate(true)}>添加数据源</button>}</header>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <div className="source-layout"><section className="source-list"><h3>当前公司的数据源</h3>{sources.length ? sources.map((source) => <button key={source.id} className={source.id === selected?.id ? "source-row active" : "source-row"} onClick={() => void loadSnapshots(source)}><span><strong>{source.name}</strong><small>{source.connection.host} · {source.connection.database}</small></span><em className={`status status-${source.status}`}>{statusLabel(source.status)}</em></button>) : <div className="empty-state">尚未配置数据源。管理员可添加只读数据库连接。</div>}</section>
      <section className="source-detail">{selected ? <><header><div><p className="kicker">数据源 #{selected.id}</p><h3>{selected.name}</h3></div><span className={`status status-${selected.status}`}>{statusLabel(selected.status)}</span></header><dl className="connection-grid"><div><dt>数据库类型</dt><dd>{selected.dialect}</dd></div><div><dt>主机与端口</dt><dd>{selected.connection.host}:{selected.connection.port}</dd></div><div><dt>数据库 / Schema</dt><dd>{selected.connection.database} / {selected.connection.schema}</dd></div><div><dt>只读账号</dt><dd>{selected.connection.user}</dd></div><div><dt>凭据环境变量</dt><dd><code>{selected.credential_env_var}</code></dd></div></dl>{selected.last_error && <p className="inline-error">{selected.last_error}</p>}<div className="detail-toolbar"><div><h4>契约快照</h4><p>选择一个版本作为后续分析的运行边界。</p></div>{canManage && <button className="quiet-button" disabled={busy} onClick={() => void discover()}>{busy ? "正在发现…" : "发现新快照"}</button>}</div><div className="snapshot-list">{snapshots.length ? snapshots.map((snapshot) => <article key={snapshot.id} className={snapshot.id === selected.active_schema_snapshot_id ? "snapshot current" : "snapshot"}><div><strong>版本 #{snapshot.id}</strong>{snapshot.id === selected.active_schema_snapshot_id && <span>当前运行版本</span>}<small>指纹 {snapshot.fingerprint.slice(0, 14)}… · {formatDate(snapshot.created_at)}</small></div>{canManage && <button className="text-button" disabled={busy || snapshot.id === selected.active_schema_snapshot_id} onClick={() => void activate(snapshot)}>{snapshot.id === selected.active_schema_snapshot_id ? "正在使用" : "设为当前版本"}</button>}</article>) : <div className="empty-state">还没有契约快照。{canManage ? "请先执行“发现新快照”。" : "请联系管理员发现并选择运行版本。"}</div>}</div></> : <div className="empty-state">选择一个数据源以查看其数据库配置与快照。</div>}</section></div>
    {showCreate && <div className="dialog-backdrop"><form className="dialog" onSubmit={create}><header><div><p className="kicker">管理员操作</p><h3>添加只读数据源</h3></div><button type="button" className="text-button" onClick={() => setShowCreate(false)}>关闭</button></header><label>数据源名称<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><div className="form-grid"><label>主机<input required value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} /></label><label>端口<input required type="number" min="1" max="65535" value={form.port} onChange={(event) => setForm({ ...form, port: event.target.value })} /></label><label>数据库<input required value={form.database} onChange={(event) => setForm({ ...form, database: event.target.value })} /></label><label>Schema<input required value={form.schema} onChange={(event) => setForm({ ...form, schema: event.target.value })} /></label><label>只读用户名<input required value={form.user} onChange={(event) => setForm({ ...form, user: event.target.value })} /></label><label>凭据环境变量<input required pattern="[A-Z][A-Z0-9_]*" value={form.credential_env_var} onChange={(event) => setForm({ ...form, credential_env_var: event.target.value.toUpperCase() })} placeholder="ACME_READONLY_PASSWORD" /></label></div><p className="muted">密码不会提交到浏览器；部署环境必须提供同名的凭据变量。</p><button className="primary-button" disabled={busy}>{busy ? "正在保存…" : "创建数据源"}</button></form></div>}
  </main>;
}

function AccountPage({ api, user, members, applications, invitations, refreshUser, refreshMembers, refreshApplications, refreshInvitations }: { api: ApiClient; user: CurrentUser; members: CompanyMember[]; applications: MembershipApplication[]; invitations: CompanyInvitation[]; refreshUser: () => Promise<void>; refreshMembers: () => Promise<void>; refreshApplications: () => Promise<void>; refreshInvitations: () => Promise<void> }) {
  const [name, setName] = useState(user.name); const [oldPassword, setOldPassword] = useState(""); const [newPassword, setNewPassword] = useState(""); const [invitationMaxUses, setInvitationMaxUses] = useState("1"); const [invitationExpiresAt, setInvitationExpiresAt] = useState(""); const [latestInvitation, setLatestInvitation] = useState<CreatedCompanyInvitation | null>(null); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [saving, setSaving] = useState(false);
  const isAdmin = user.role === "owner" || user.role === "admin";
  useEffect(() => { if (isAdmin) void Promise.all([refreshApplications(), refreshInvitations()]).catch((reason) => setError(toChineseError(reason))); }, [isAdmin, refreshApplications, refreshInvitations]);
  useEffect(() => setName(user.name), [user.name]);
  async function updateProfile(event: FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { await api.updateMe(name); await refreshUser(); setNotice("个人信息已更新。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  async function updatePassword(event: FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { await api.changePassword(oldPassword, newPassword); setOldPassword(""); setNewPassword(""); setNotice("密码已更新，其他已登录设备将需要重新登录。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  async function updateMember(member: CompanyMember, patch: Partial<Pick<CompanyMember, "role" | "status">>) { setSaving(true); setError(""); try { await api.updateMember(member.id, patch); await refreshMembers(); setNotice("成员权限已更新。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  async function createInvitation(event: FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { const expires_at = invitationExpiresAt ? new Date(invitationExpiresAt).toISOString() : undefined; const invitation = await api.createInvitation({ max_uses: Number(invitationMaxUses), ...(expires_at ? { expires_at } : {}) }); setLatestInvitation(invitation); await refreshInvitations(); setNotice("邀请码已创建。请仅通过受控渠道分享下方代码。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  async function revokeInvitation(invitation: CompanyInvitation) { if (!window.confirm("确定撤销此邀请码吗？撤销后它不能再用于提交申请。")) return; setSaving(true); setError(""); try { await api.revokeInvitation(invitation.id); await refreshInvitations(); setNotice("邀请码已撤销。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  async function reviewApplication(application: MembershipApplication, decision: "approve" | "reject") { setSaving(true); setError(""); try { if (decision === "approve") await api.approveMembershipApplication(application.id); else await api.rejectMembershipApplication(application.id); await refreshApplications(); await refreshMembers(); setNotice(decision === "approve" ? "申请已批准，用户现在可以登录。" : "申请已拒绝。"); } catch (reason) { setError(toChineseError(reason)); } finally { setSaving(false); } }
  return <main className="page-content"><header className="page-header"><div><p className="kicker">账户与权限</p><h2>用户中心</h2><p>你的账户属于 {user.company_name}；权限由后端成员关系统一校验。</p></div><span className="role-badge">{user.role === "owner" ? "所有者" : user.role === "admin" ? "管理员" : user.role === "analyst" ? "分析员" : "查看者"}</span></header>{error && <p className="inline-error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    <div className="account-grid"><section className="account-card"><h3>个人信息</h3><form onSubmit={updateProfile}><label>显示名称<input value={name} onChange={(event) => setName(event.target.value)} required /></label><dl><div><dt>用户名</dt><dd>{user.username}</dd></div><div><dt>公司</dt><dd>{user.company_name}</dd></div><div><dt>成员状态</dt><dd>{statusLabel(user.membership_status)}</dd></div></dl><button className="primary-button" disabled={saving}>保存个人信息</button></form></section><section className="account-card"><h3>安全设置</h3><form onSubmit={updatePassword}><label>当前密码<input type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} required minLength={8} /></label><label>新密码<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={8} /></label><button className="quiet-button" disabled={saving}>更新密码</button></form></section></div>
    {isAdmin && <section className="members-section"><header><div><p className="kicker">管理员操作</p><h3>邀请码与入职申请</h3><p>邀请码只在创建后显示一次；申请人必须经审核批准后才能登录。</p></div></header><div className="account-grid invite-grid"><section><form className="invite-form" onSubmit={createInvitation}><label>最大使用次数<input type="number" min="1" max="1000" value={invitationMaxUses} onChange={(event) => setInvitationMaxUses(event.target.value)} required /></label><label>过期时间（可选）<input type="datetime-local" value={invitationExpiresAt} onChange={(event) => setInvitationExpiresAt(event.target.value)} /></label><button className="primary-button" disabled={saving}>创建邀请码</button></form>{latestInvitation && <div className="invitation-code"><strong>新邀请码</strong><code>{latestInvitation.code}</code><small>最多使用 {latestInvitation.max_uses} 次{latestInvitation.expires_at ? `，截至 ${formatDate(latestInvitation.expires_at)}` : "，未设置过期时间"}。</small></div>}<div className="invitation-list"><h4>邀请码状态</h4>{invitations.length ? invitations.map((invitation) => <article key={invitation.id}><div><strong>邀请码 #{invitation.id}</strong><small>已使用 {invitation.used_count} / {invitation.max_uses} 次 · 创建于 {formatDate(invitation.created_at)}{invitation.expires_at ? ` · 截至 ${formatDate(invitation.expires_at)}` : ""}</small></div><div><span className={`status status-${invitation.is_active ? "approved" : "disabled"}`}>{invitation.is_active ? "可用" : "已撤销"}</span>{invitation.is_active && <button className="text-button reject-button" disabled={saving} onClick={() => void revokeInvitation(invitation)}>撤销</button>}</div></article>) : <p className="muted">尚未创建邀请码。</p>}</div></section><section className="application-queue"><h4>待审核申请</h4>{applications.length ? <div className="application-list">{applications.map((application) => <article key={application.id}><div><strong>{application.user_name || `用户 #${application.user_id}`}</strong><small>{application.username ? `@${application.username}` : `用户 #${application.user_id}`} · 提交于 {formatDate(application.created_at)}</small></div><div><button className="text-button" disabled={saving} onClick={() => void reviewApplication(application, "approve")}>批准</button><button className="text-button reject-button" disabled={saving} onClick={() => void reviewApplication(application, "reject")}>拒绝</button></div></article>)}</div> : <p className="muted">当前没有待审核申请。</p>}</section></div></section>}
    {isAdmin && <section className="members-section"><header><div><p className="kicker">管理员操作</p><h3>公司成员</h3><p>可以查看成员、调整角色，或禁用及恢复访问。所有者角色受后端的最后所有者保护规则约束。</p></div></header><div className="member-table"><div className="member-head"><span>用户</span><span>角色</span><span>状态</span><span>加入时间</span><span>操作</span></div>{members.map((member) => <div className="member-row" key={member.id}><strong>{member.user_name}{member.user_id === user.id ? "（你）" : ""}<small>{member.username ? `@${member.username}` : `用户 #${member.user_id}`}</small></strong><select aria-label={`成员 ${member.user_name} 的角色`} value={member.role} disabled={saving} onChange={(event) => void updateMember(member, { role: event.target.value as CompanyMember["role"] })}><option value="owner">所有者</option><option value="admin">管理员</option><option value="analyst">分析员</option><option value="viewer">查看者</option></select><span className={`status status-${member.status}`}>{statusLabel(member.status)}</span><small>{formatDate(member.created_at)}</small>{member.status === "disabled" ? <button className="text-button" disabled={saving} onClick={() => void updateMember(member, { status: "approved" })}>启用</button> : <button className="text-button reject-button" disabled={saving} onClick={() => void updateMember(member, { status: "disabled" })}>禁用</button>}</div>)}</div></section>}
  </main>;
}

function Workspace({ token, onLogout }: { token: string; onLogout: () => void }) {
  const api = useMemo(() => new ApiClient(token), [token]);
  const [user, setUser] = useState<CurrentUser | null>(null); const [sources, setSources] = useState<DataSource[]>([]); const [assistantSources, setAssistantSources] = useState<AssistantDataSource[]>([]); const [documents, setDocuments] = useState<DocumentItem[]>([]); const [conversations, setConversations] = useState<Conversation[]>([]); const [members, setMembers] = useState<CompanyMember[]>([]); const [applications, setApplications] = useState<MembershipApplication[]>([]); const [invitations, setInvitations] = useState<CompanyInvitation[]>([]); const [page, setPage] = useState<Page>("assistant"); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const refreshUser = useCallback(async () => setUser(await api.me()), [api]); const refreshSources = useCallback(async () => setSources(await api.dataSources()), [api]); const refreshDocuments = useCallback(async () => setDocuments(await api.documents()), [api]); const refreshConversations = useCallback(async () => setConversations(await api.conversations()), [api]); const refreshMembers = useCallback(async () => setMembers(await api.members()), [api]); const refreshApplications = useCallback(async () => setApplications(await api.membershipApplications("pending")), [api]); const refreshInvitations = useCallback(async () => setInvitations(await api.invitations()), [api]);
  const refreshAll = useCallback(async () => { try { const current = await api.me(); setUser(current); const [nextAssistantSources, nextDocuments, nextConversations] = await Promise.all([api.assistantDataSources(), api.documents(), api.conversations()]); setAssistantSources(nextAssistantSources); setDocuments(nextDocuments); setConversations(nextConversations); if (current.role === "owner" || current.role === "admin") { const [nextSources, nextMembers, nextApplications, nextInvitations] = await Promise.all([api.dataSources(), api.members(), api.membershipApplications("pending"), api.invitations()]); setSources(nextSources); setMembers(nextMembers); setApplications(nextApplications); setInvitations(nextInvitations); } else { setSources([]); setMembers([]); setApplications([]); setInvitations([]); } } catch (reason) { setError(toChineseError(reason)); if (reason instanceof ApiError && reason.status === 401) onLogout(); } finally { setLoading(false); } }, [api, onLogout]);
  useEffect(() => { void refreshAll(); }, [refreshAll]);
  if (loading) return <main className="app-loading"><span className="loading-line" /><p>正在加载当前公司工作台…</p></main>;
  if (!user) return <main className="app-loading"><p className="inline-error">{error || "无法读取当前账户。"}</p></main>;
  const canManageSources = user.role === "owner" || user.role === "admin";
  return <div className="app-shell"><aside className="app-nav"><div className="nav-brand"><span className="brand-mark">EI</span><span>经营洞察</span></div><nav><button className={page === "assistant" ? "nav-link active" : "nav-link"} onClick={() => setPage("assistant")}>经营助手</button><button className={page === "documents" ? "nav-link active" : "nav-link"} onClick={() => setPage("documents")}>文档知识库</button>{canManageSources && <button className={page === "sources" ? "nav-link active" : "nav-link"} onClick={() => setPage("sources")}>数据源管理</button>}<button className={page === "account" ? "nav-link active" : "nav-link"} onClick={() => setPage("account")}>用户中心</button></nav><div className="nav-user"><strong>{user.name}</strong><span>{user.company_name}</span><button className="text-button" onClick={() => void api.logout().catch(() => undefined).finally(onLogout)}>退出登录</button></div></aside><section className="app-surface">{error && <p className="global-error" role="alert">{error}</p>}{page === "assistant" && <AssistantPage api={api} sources={assistantSources} documents={documents} conversations={conversations} refreshConversations={refreshConversations} />}{page === "documents" && <DocumentPage api={api} documents={documents} refreshDocuments={refreshDocuments} />}{page === "sources" && canManageSources && <SourcePage api={api} sources={sources} refresh={refreshSources} canManage={canManageSources} />}{page === "account" && <AccountPage api={api} user={user} members={members} applications={applications} invitations={invitations} refreshUser={refreshUser} refreshMembers={refreshMembers} refreshApplications={refreshApplications} refreshInvitations={refreshInvitations} />}</section></div>;
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY));
  return token ? <Workspace token={token} onLogout={() => { sessionStorage.removeItem(TOKEN_KEY); setToken(null); }} /> : <LoginScreen onLoggedIn={(next) => { sessionStorage.setItem(TOKEN_KEY, next); setToken(next); }} />;
}
