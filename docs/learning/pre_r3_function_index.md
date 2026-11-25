# 附录：R3 之前（e60bb4e）backend/app 全部函数和类清单

由脚本从提交 e60bb4e 自动生成。每行：名字、起止行、参数和返回类型、docstring 第一行（没有就空着）。

## `backend/app/core/celery_app.py`（79 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_setup_celery_tracing(**_kwargs) -> None` | 15-17 | Only Celery processes are agent-celery; the API imports this module too. |
| 函数 `_use_project_logging(**_kwargs) -> None` | 21-23 | Replace Celery's plain-text root handler with redacted JSON logging. |

## `backend/app/core/config/admission.py`（44 行）

模块说明：How many analysis tasks may run, and the disk-capacity admission signal.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AdmissionConfig`(ConfigDomain) | 13-44 |  |
| 函数 `AdmissionConfig.admission_validate_positive_int(value) -> int` | 33-34 |  |
| 函数 `AdmissionConfig.admission_validate_capacity_signal_timeout(value) -> int` | 38-44 |  |

## `backend/app/core/config/app.py`（39 行）

模块说明：Application identity, environment, logging and CORS.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AppConfig`(ConfigDomain) | 13-32 |  |
| 函数 `AppConfig.app_resolve_log_dir(value) -> Path` | 31-32 |  |
| 函数 `resolve_backend_path(value) -> Path` | 35-39 |  |

## `backend/app/core/config/artifacts.py`（89 行）

模块说明：Document uploads and input artifacts.  The upload entry is frozen (AGENTS.md):

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ArtifactConfig`(ConfigDomain) | 11-89 |  |
| 函数 `ArtifactConfig.artifacts_normalize_optional_object_storage_public_endpoint(value) -> str \| None` | 44-47 |  |
| 函数 `ArtifactConfig.artifacts_validate_positive_int(value) -> int` | 67-68 |  |
| 函数 `ArtifactConfig.artifacts_validate_object_storage_health_timeout(value) -> int` | 72-75 |  |
| 函数 `ArtifactConfig.artifacts_validate_ocr_confidence(value) -> float` | 79-82 |  |
| 函数 `ArtifactConfig.artifacts_validate_ocr_languages(value) -> str` | 86-89 |  |

## `backend/app/core/config/base.py`（37 行）

模块说明：Shared pieces of the configuration domains (K1).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConfigDomain`(BaseModel) | 18-19 |  |
| 函数 `require_positive(value) -> int` | 22-25 |  |
| 函数 `require_non_negative(value) -> int` | 28-31 |  |
| 函数 `require_score(value) -> float` | 34-37 |  |

## `backend/app/core/config/catalog.py`（193 行）

模块说明：Configuration catalog: every setting the platform reads, by domain (K2).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConfigItem`() | 90-94 |  |
| 函数 `_render(value) -> str` | 97-110 |  |
| 函数 `catalog() -> list[ConfigItem]` | 113-124 |  |
| 函数 `declared_names() -> set[str]` | 127-128 |  |
| 函数 `_prefixes(names) -> set[str]` | 131-132 |  |
| 函数 `unknown_keys(env_file_keys, environ, *, credential_names) -> list[str]` | 135-149 | Names no setting declares: every key of the env file, and process |
| 函数 `render_example() -> str` | 152-166 |  |
| 函数 `main(argv) -> int` | 169-189 |  |

## `backend/app/core/config/context.py`（56 行）

模块说明：How much conversation history and evidence a model prompt may carry.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ContextConfig`(ConfigDomain) | 12-56 |  |
| 函数 `ContextConfig.context_validate_positive_int(value) -> int` | 48-49 |  |
| 函数 `ContextConfig.context_validate_share(value) -> float` | 53-56 |  |

## `backend/app/core/config/flags.py`（13 行）

模块说明：Feature switches decided per deployment.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `FeatureFlags`(ConfigDomain) | 10-13 |  |

## `backend/app/core/config/infra.py`（65 行）

模块说明：Platform database, business database, Redis and local storage.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `InfraConfig`(ConfigDomain) | 18-65 |  |
| 函数 `InfraConfig.infra_resolve_storage_dir(value) -> Path` | 38-39 |  |
| 函数 `InfraConfig.infra_validate_positive_int(value) -> int` | 43-44 |  |
| 函数 `InfraConfig.infra_validate_non_negative_int(value) -> int` | 48-49 |  |
| 函数 `InfraConfig.upload_dir() -> Path` | 52-53 |  |
| 函数 `InfraConfig.input_artifact_quarantine_dir() -> Path` | 56-57 |  |
| 函数 `InfraConfig.knowledge_dir() -> Path` | 60-61 |  |
| 函数 `InfraConfig.faiss_dir() -> Path` | 64-65 |  |

## `backend/app/core/config/memory.py`（23 行）

模块说明：Long-term memory: Planner budget, expiry and purge of deleted items.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MemoryConfig`(ConfigDomain) | 10-23 |  |
| 函数 `MemoryConfig.memory_validate_positive_int(value) -> int` | 22-23 |  |

## `backend/app/core/config/model.py`（68 行）

模块说明：Model provider, per-task model budget and node retry counts.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ModelConfig`(ConfigDomain) | 17-68 |  |
| 函数 `ModelConfig.model_validate_positive_int(value) -> int` | 46-47 |  |
| 函数 `ModelConfig.model_validate_non_negative_model_repairs(value) -> int` | 51-52 |  |
| 函数 `ModelConfig.model_validate_positive_model_cost(value) -> Decimal` | 56-59 |  |
| 函数 `ModelConfig.model_validate_llm_timeout_against_execution_lease(value) -> int` | 63-68 |  |

## `backend/app/core/config/rag.py`（32 行）

模块说明：Document retrieval and reranking.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RagConfig`(ConfigDomain) | 12-32 |  |
| 函数 `RagConfig.rag_validate_positive_int(value) -> int` | 26-27 |  |
| 函数 `RagConfig.rag_validate_score(value) -> float` | 31-32 |  |

## `backend/app/core/config/security.py`（45 行）

模块说明：Authentication, request rate limits and data-source egress rules.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SecurityConfig`(ConfigDomain) | 12-45 |  |
| 函数 `SecurityConfig.security_validate_positive_int(value) -> int` | 44-45 |  |

## `backend/app/core/config/settings.py`（184 行）

模块说明：``Settings`` combines every configuration domain (K1).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Settings`(AppConfig, InfraConfig, SecurityConfig, AdmissionConfig, ModelConfig, ToolConfig, ContextConfig, MemoryConfig, RagConfig, FeatureFlags, ArtifactConfig, BaseSettings) | 56-149 |  |
| 函数 `Settings.domain(domain) -> DomainT` | 78-81 | One domain's effective values, e.g. ``settings.domain(RagConfig)``. |
| 函数 `Settings.validate_database_password() -> Self` | 84-149 |  |
| 函数 `check_known_keys(settings, *, env_file, environ) -> list[str]` | 152-177 | K2: refuse names no setting declares; the test environment only warns. |
| 函数 `get_settings() -> Settings` | 181-184 |  |

## `backend/app/core/config/snapshot.py`（84 行）

模块说明：K4: a task's business configuration, frozen when the task is created.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `build_config_snapshot(settings) -> dict[str, Any]` | 38-43 |  |
| 函数 `config_snapshot_hash(snapshot) -> str` | 46-50 |  |
| 函数 `settings_from_snapshot(snapshot) -> Settings` | 53-70 | Current settings with the snapshot's business values applied. |
| 函数 `task_config_scope(snapshot) -> Iterator[Settings]` | 74-79 |  |
| 函数 `runtime_settings() -> Settings` | 82-84 | Business settings for the running task; ``get_settings()`` outside one. |

## `backend/app/core/config/tool.py`（47 行）

模块说明：Model-chosen tools inside Data and Knowledge, and the tool loop limits.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ToolConfig`(ConfigDomain) | 12-47 |  |
| 函数 `ToolConfig.tool_validate_positive_int(value) -> int` | 34-35 |  |
| 函数 `ToolConfig.tool_validate_non_negative_int(value) -> int` | 39-40 |  |
| 函数 `ToolConfig.tool_validate_seconds(value) -> float` | 44-47 |  |

## `backend/app/core/error_handling.py`（83 行）

模块说明：错误处理与重试 —— 异常分类 + 指数退避重试

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `classify_exception(exc) -> str` | 15-21 | 判断异常是可重试的还是永久性的 |
| 函数 `_record_failure()` | 24-27 |  |
| 函数 `_record_success()` | 30-32 |  |
| 函数 `retry_with_backoff(func, max_retries, base_delay)` | 35-72 | 指数退避重试。 |
| 函数 `_check_circuit_breaker()` | 75-83 | 检查是否在熔断状态 |

## `backend/app/core/exceptions.py`（239 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `localize_error_message(message) -> str` | 49-51 | Return a safe Chinese message without exposing backend implementation text. |
| 函数 `localize_validation_error(error_type) -> str` | 54-55 |  |
| 类 `RetrievalError`(RuntimeError) | 58-59 | RAG 检索过程失败。 |
| 类 `EmbeddingError`(RetrievalError) | 62-63 | 生成查询向量失败。 |
| 类 `VectorSearchError`(RetrievalError) | 66-67 | 向量数据库检索失败。 |
| 类 `RerankingError`(RetrievalError) | 70-71 | 候选文档重排失败。 |
| 类 `RetryableModelError`(Exception) | 74-75 |  |
| 类 `MalformedModelResponseError`(RetryableModelError) | 78-79 | The provider returned a response that violates the gateway contract. |
| 类 `PermanentModelError`(Exception) | 82-83 |  |
| 类 `StructuredOutputError`(ValueError) | 86-87 | 模型输出无法解析为约定的结构化结果。 |
| 类 `DocumentUploadError`(Exception) | 90-91 |  |
| 类 `InsufficientStorageError`(DocumentUploadError) | 94-95 | The application storage volume cannot accept another file. |
| 类 `EmptyDocumentError`(DocumentUploadError) | 98-99 |  |
| 类 `UnsupportedDocumentTypeError`(DocumentUploadError) | 102-103 |  |
| 类 `DocumentTooLargeError`(DocumentUploadError) | 106-107 |  |
| 类 `InvalidDocumentNameError`(DocumentUploadError) | 110-111 |  |
| 类 `DuplicateDocumentError`(DocumentUploadError) | 114-115 |  |
| 类 `InputArtifactUploadError`(Exception) | 118-119 |  |
| 类 `EmptyInputArtifactError`(InputArtifactUploadError) | 122-123 |  |
| 类 `UnsupportedInputArtifactTypeError`(InputArtifactUploadError) | 126-127 |  |
| 类 `InputArtifactTooLargeError`(InputArtifactUploadError) | 130-131 |  |
| 类 `InvalidInputArtifactNameError`(InputArtifactUploadError) | 134-135 |  |
| 类 `TaskCannotBeCancelledError`(Exception) | 138-139 |  |
| 类 `TaskAdmissionLimitError`(Exception) | 142-147 |  |
| 函数 `TaskAdmissionLimitError.__init__(*, scope, limit, retry_after_seconds) -> None` | 143-147 |  |
| 类 `TaskCapacityAdmissionError`(Exception) | 150-153 |  |
| 函数 `TaskCapacityAdmissionError.__init__(*, retry_after_seconds) -> None` | 151-153 |  |
| 类 `TaskCapacitySignalUnavailableError`(TaskCapacityAdmissionError) | 156-157 |  |
| 类 `TaskCapacityLowWatermarkError`(TaskCapacityAdmissionError) | 160-161 |  |
| 异步函数 `unhandled_exception_handler(request, _exc) -> JSONResponse` | 164-181 |  |
| 异步函数 `http_exception_handler(request, exc) -> JSONResponse` | 184-210 |  |
| 异步函数 `request_validation_handler(request, exc) -> JSONResponse` | 213-239 |  |

## `backend/app/core/gateway/base.py`（97 行）

模块说明：Model Gateway - AI 模型调用网关

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ModelCallRecord`() | 18-30 | 一次模型调用的完整记录 |
| 类 `ToolCall`() | 34-39 | 模型想调用的一个工具；arguments 是模型写的原始 JSON 文本，尚未校验。 |
| 类 `ToolChatResponse`() | 43-61 | 一轮工具对话的回复：要么有工具调用，要么是模型的文字回答。 |
| 函数 `ToolChatResponse.assistant_message() -> dict` | 49-61 | 这轮回复放回对话历史时的格式，下一轮模型靠它对应工具结果。 |
| 类 `ToolCallingUnsupportedError`(PermanentModelError) | 64-65 | 当前网关没有实现原生工具调用。 |
| 类 `ModelGateway`(ABC) | 68-97 | 模型网关抽象类 - 所有模型提供者都要实现这个接口 |
| 函数 `ModelGateway.chat(prompt, system_prompt, *, json_mode) -> str` | 72-80 | 发送对话请求；json_mode 要求模型返回一个 JSON 对象。 |
| 函数 `ModelGateway.chat_with_tools(messages, tools, *, tool_choice) -> ToolChatResponse` | 82-92 | 原生工具调用；没有实现的网关明确拒绝，由调用方退回固定路线。 |
| 函数 `ModelGateway.count_tokens(text) -> int` | 95-97 | 计算一段文本的 Token 数量 |

## `backend/app/core/gateway/deepseek.py`（367 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_response_details(response, usage) -> dict` | 45-55 | What the provider says beyond tokens: was it cut off, who answered, cache use. |
| 类 `DeepSeekGateway`(ModelGateway) | 58-367 |  |
| 函数 `DeepSeekGateway.__init__(model_name)` | 59-75 |  |
| 函数 `DeepSeekGateway.chat(prompt, system_prompt, *, json_mode) -> str` | 77-88 |  |
| 函数 `DeepSeekGateway.chat_with_tools(messages, tools, *, tool_choice) -> ToolChatResponse` | 90-109 |  |
| 函数 `DeepSeekGateway._chat_once(prompt, system_prompt, *, json_mode, messages, tools, tool_choice) -> str \| ToolChatResponse` | 112-337 |  |
| 函数 `DeepSeekGateway.count_tokens(text) -> int` | 339-340 |  |
| 函数 `DeepSeekGateway._log_failure(*, prompt, create_at, exc) -> None` | 342-367 |  |

## `backend/app/core/gateway/factory.py`（21 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_model_gateway() -> ModelGateway` | 11-21 |  |

## `backend/app/core/gateway/local.py`（103 行）

模块说明：本地模拟 Model Gateway - 不调用真实 AI 模型，直接返回模拟结果

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `LocalModelGateway`(ModelGateway) | 23-103 | 本地模拟网关 - 假装调用了 AI 模型，实际上返回固定文本 |
| 函数 `LocalModelGateway.chat(prompt, system_prompt, *, json_mode) -> str` | 26-99 | 模拟 AI 对话 |
| 函数 `LocalModelGateway.count_tokens(text) -> int` | 101-103 | 估算 Token 数量（按字符数估算） |

## `backend/app/core/gateway/openai.py`（263 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `OpenAIGateway`(ModelGateway) | 38-263 |  |
| 函数 `OpenAIGateway.__init__(model_name)` | 39-51 |  |
| 函数 `OpenAIGateway.chat(prompt, system_prompt, *, json_mode) -> str` | 53-61 |  |
| 函数 `OpenAIGateway._chat_once(prompt, system_prompt, *, json_mode) -> str` | 64-232 |  |
| 函数 `OpenAIGateway.count_tokens(text) -> int` | 234-237 |  |
| 函数 `OpenAIGateway._log_failure(*, prompt, create_at, exc) -> None` | 239-263 |  |

## `backend/app/core/gateway/replay.py`（124 行）

模块说明：Record-once, replay-offline model gateway for component evaluation.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ReplayMissError`(RuntimeError) | 26-27 | Raised when replay mode has no recording for the exact request. |
| 函数 `request_key(prompt, system_prompt, *, json_mode) -> str` | 30-32 |  |
| 类 `RecordReplayGateway`(ModelGateway) | 35-124 |  |
| 函数 `RecordReplayGateway.__init__(cassette_dir, *, mode, inner) -> None` | 36-48 |  |
| 函数 `RecordReplayGateway._path(key) -> Path` | 50-51 |  |
| 函数 `RecordReplayGateway.chat(prompt, system_prompt, *, json_mode) -> str` | 53-78 |  |
| 函数 `RecordReplayGateway.chat_with_tools(messages, tools, *, tool_choice) -> ToolChatResponse` | 80-118 |  |
| 函数 `RecordReplayGateway.count_tokens(text) -> int` | 120-124 |  |

## `backend/app/core/heartbeat.py`（72 行）

模块说明：Liveness heartbeats for the Celery worker and beat (O4).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `heartbeat_path(name) -> Path` | 28-29 |  |
| 函数 `touch(name) -> None` | 32-35 |  |
| 函数 `heartbeat_age_seconds(name, *, now) -> float \| None` | 38-44 | Seconds since the last heartbeat, or None when there has been none. |
| 类 `WorkerHeartbeat`(bootsteps.StartStopStep) | 47-64 | Touch ``worker.heartbeat`` from the worker timer (main event loop). |
| 函数 `WorkerHeartbeat.__init__(worker, **kwargs) -> None` | 52-54 |  |
| 函数 `WorkerHeartbeat.start(worker) -> None` | 56-60 |  |
| 函数 `WorkerHeartbeat.stop(worker) -> None` | 62-64 |  |
| 类 `HeartbeatScheduler`(PersistentScheduler) | 67-72 | Beat's default scheduler that also touches ``beat.heartbeat`` per tick. |
| 函数 `HeartbeatScheduler.tick(*args, **kwargs)` | 70-72 |  |

## `backend/app/core/logging.py`（127 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_component(logger_name) -> str` | 22-27 | app.modules.<component>.… → <component>; other loggers keep their root. |
| 类 `JsonFormatter`(logging.Formatter) | 30-95 |  |
| 函数 `JsonFormatter.format(record) -> str` | 31-95 |  |
| 函数 `build_console_formatter() -> logging.Formatter` | 98-100 | Container stdout uses the same redacted one-line JSON as the log file. |
| 函数 `configure_logging(settings) -> None` | 103-127 |  |

## `backend/app/core/middleware.py`（133 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_is_audited_analysis_rejection(request, response) -> bool` | 22-28 |  |
| 函数 `_check_rate_limit(api_key) -> JSONResponse \| None` | 31-59 | 检查 API Key 是否超过频率限制。超限返回 429，未超限返回 None。 |
| 异步函数 `request_context_middleware(request, call_next) -> Response` | 62-133 |  |

## `backend/app/core/redaction.py`（20 行）

模块说明：Shared sensitive-text patterns for logs and task traces.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `redact_text(text) -> str` | 18-20 | Replace each sensitive match so the surrounding message stays readable. |

## `backend/app/core/security.py`（35 行）

模块说明：Secrets used by the platform authentication boundary.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `hash_api_key(api_key) -> str` | 14-16 | Return the database representation of a high-entropy API key. |
| 函数 `generate_api_key() -> str` | 19-21 | Generate an API key that is shown to the caller exactly once. |
| 函数 `hash_password(password) -> str` | 24-26 | Hash a password with Argon2; plaintext is never persisted. |
| 函数 `verify_password(password, password_hash) -> bool` | 29-35 |  |

## `backend/app/core/tokenizer.py`（50 行）

模块说明：One place that counts tokens (C1).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_encoding(name) -> tiktoken.Encoding` | 22-23 |  |
| 函数 `encoding_for_model(model_name, *, fallback) -> tiktoken.Encoding` | 26-35 | The model's own encoding; models tiktoken does not know (DeepSeek) use |
| 函数 `count_tokens(text, *, model_name) -> int` | 38-40 |  |
| 函数 `preload() -> None` | 43-46 | Download every bundled encoding (run at image build time). |

## `backend/app/core/tracing.py`（160 行）

模块说明：Distributed tracing with OpenTelemetry (O1).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `safe_attributes(attributes) -> dict[str, str \| int \| float \| bool]` | 61-69 | Keep allowlisted keys with scalar values; drop everything else. |
| 函数 `setup_tracing(service_name, *, processor) -> TracerProvider` | 72-91 | Create this process's tracer provider.  The batch processor restarts its |
| 函数 `tracer() -> trace.Tracer` | 94-97 |  |
| 函数 `current_traceparent() -> str \| None` | 100-103 |  |
| 函数 `span(name, *, traceparent, attributes) -> Iterator[Span]` | 107-132 | A span with allowlisted attributes; ``traceparent`` continues a stored |
| 函数 `set_attributes(current, attributes) -> None` | 135-136 |  |
| 函数 `traced_model_call(system) -> Callable[[F], F]` | 142-160 | One ``gen_ai.chat`` span per physical provider call.  Token counts per |

## `backend/app/core/watchdog.py`（139 行）

模块说明：Run a Celery process and exit when its heartbeat goes stale (O4).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `stale_reason(name, *, started_at, now, max_age, startup_grace) -> str \| None` | 34-52 | Why the heartbeat counts as stale, or None while it is fresh. |
| 函数 `_stop(child, sig) -> None` | 55-63 |  |
| 函数 `supervise(command, name, *, max_age, startup_grace, clock, sleep) -> int` | 66-107 |  |
| 函数 `main(argv) -> int` | 110-135 |  |

## `backend/app/db/base.py`（14 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Base`(DeclarativeBase) | 13-14 |  |

## `backend/app/db/clock.py`（13 行）

模块说明：Database-authoritative timestamps for cross-process lease decisions.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `database_now(db) -> datetime` | 9-13 |  |

## `backend/app/db/errors.py`（30 行）

模块说明：Classify platform-database failures that a retry can reasonably fix.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_is_connection_failure(exc) -> bool` | 8-11 |  |
| 函数 `is_transient_database_error(exc) -> bool` | 14-30 | True when a lost or invalidated connection is the root of this failure. |

## `backend/app/db/session.py`（77 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `set_tenant_scope(db, company_id) -> None` | 35-55 | Bind a Session to one company for the current and later transactions. |
| 函数 `_apply_tenant_scope_on_transaction_start(session, transaction, connection) -> None` | 59-69 | Reapply the tenant GUC after commits when a scoped Session is reused. |
| 函数 `get_db() -> Generator[Session, None, None]` | 72-77 |  |

## `backend/app/main.py`（69 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 异步函数 `lifespan(app)` | 26-43 |  |

## `backend/app/modules/analysis/agent_protocol.py`（58 行）

模块说明：Agent 协议 —— 所有 Agent 必须实现这个接口

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AgentInput`() | 11-16 | 一次 Agent 调用的输入 |
| 类 `AgentOutput`() | 20-31 | 一次 Agent 调用的输出 |
| 类 `Agent`(ABC) | 34-58 | Agent 基类 —— 所有 Agent 必须实现下面这些属性和方法 |
| 函数 `Agent.name() -> str` | 39-41 | Agent 名称，如 'knowledge'、'data'、'planner'、'reviewer' |
| 函数 `Agent.description() -> str` | 45-47 | Agent 描述，说明这个 Agent 的职责 |
| 函数 `Agent.allowed_tools() -> list[Tool]` | 51-53 | 这个 Agent 可以调用的工具列表 |
| 函数 `Agent.run(input) -> AgentOutput` | 56-58 | 执行 Agent，输入问题，返回结果 |

## `backend/app/modules/analysis/catalog/schema_discovery.py`（89 行）

模块说明：Read PostgreSQL metadata into a tenant-scoped query catalog.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `discover_postgres_schema(source) -> tuple[dict, str]` | 13-89 |  |

## `backend/app/modules/analysis/catalog/schema_selection.py`（125 行）

模块说明：Pick the part of a schema snapshot worth showing the model for one question.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_join_neighbours(catalog) -> dict[str, set[str]]` | 64-69 |  |
| 函数 `_path_between(start, targets, neighbours) -> list[str]` | 72-93 | Shortest join path from start to any target, excluding both ends. |
| 函数 `select_tables(catalog, texts) -> set[str]` | 96-110 | Tables the question points at, plus those needed to join them; empty if unsure. |
| 函数 `narrow_catalog(catalog, tables) -> SnapshotCatalog \| None` | 113-125 | The catalog limited to these tables; None when that would not narrow it. |

## `backend/app/modules/analysis/catalog/semantic_catalog.py`（227 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `TableDefinition`() | 5-7 |  |
| 类 `JoinDefinition`() | 11-15 |  |
| 函数 `is_allowed_table(table) -> bool` | 200-201 |  |
| 函数 `allowed_columns(table) -> frozenset[str]` | 204-206 |  |
| 函数 `is_allowed_join(left_table, left_column, right_table, right_column) -> bool` | 209-227 |  |

## `backend/app/modules/analysis/catalog/snapshot_catalog.py`（81 行）

模块说明：Adapter from a persisted tenant schema snapshot to SQL validation rules.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SnapshotCatalog`() | 10-81 | Only exposes metadata discovered from one business data source. |
| 函数 `SnapshotCatalog.from_snapshot(snapshot) -> SnapshotCatalog` | 17-61 |  |
| 函数 `SnapshotCatalog.has_table(table_name) -> bool` | 63-64 |  |
| 函数 `SnapshotCatalog.columns_for(table_name) -> frozenset[str]` | 66-67 |  |
| 函数 `SnapshotCatalog.allows_join(left_table, left_column, right_table, right_column) -> bool` | 69-81 |  |

## `backend/app/modules/analysis/data/data_agent.py`（523 行）

模块说明：Data Agent —— 生成候选 SQL，并通过受控 SQL Tool 查询经营数据。

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_max_data_attempts() -> int` | 28-29 |  |
| 函数 `_concept_key(value) -> str` | 32-38 | Normalize only common measurement suffixes, not arbitrary business meaning. |
| 函数 `_make_json_safe(value)` | 41-51 |  |
| 函数 `_validated_evaluation_scope(plan) -> dict[str, object] \| None` | 54-63 |  |
| 类 `DataAgent`(Agent) | 66-523 | 只使用受控 SQL 生成服务和只读 SQL Tool 的 Agent。 |
| 函数 `DataAgent.__init__(sql_generator, sql_tool, *, data_source, snapshot_catalog, semantic_reviewer) -> None` | 69-86 |  |
| 函数 `DataAgent.name() -> str` | 89-90 |  |
| 函数 `DataAgent.description() -> str` | 93-94 |  |
| 函数 `DataAgent.allowed_tools() -> list[Tool]` | 97-98 |  |
| 函数 `DataAgent.run(input) -> AgentOutput` | 100-396 |  |
| 函数 `DataAgent._data_required_capabilities(intent) -> list[str]` | 399-406 |  |
| 函数 `DataAgent._contract_gaps(required_capabilities, contract) -> tuple[list[str], list[str]]` | 409-415 | Planned capabilities the contract misses, and ones it adds. |
| 函数 `DataAgent._build_evidence(*, sql, purpose, contract, columns, rows, assessment, claim_assessment, metric_assessment) -> dict` | 418-456 |  |
| 函数 `DataAgent._replay_validated_sql(feedback) -> AgentOutput` | 458-523 | Retry only a SQL statement that previously passed the SQL Tool boundary. |

## `backend/app/modules/analysis/data/data_request.py`（32 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DataRequest`(BaseModel) | 17-32 |  |
| 函数 `DataRequest.validate_months() -> 'DataRequest'` | 25-32 |  |

## `backend/app/modules/analysis/data/query_contract.py`（63 行）

模块说明：Contracts that separate a query executing from it proving an answer.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClarificationSpec`(BaseModel) | 19-23 | Machine-readable missing information; the UI text is rendered from it. |
| 类 `QuestionIntent`(BaseModel) | 26-36 | The business meaning the planner believes must be evidenced. |
| 类 `QueryContract`(BaseModel) | 39-48 | What one candidate query must return before it may become business evidence. |
| 类 `NumericAssertion`(BaseModel) | 51-56 | A bounded, machine-checkable numeric statement about one query result. |
| 类 `QueryResultAssessment`(BaseModel) | 59-63 | A deterministic post-execution assessment, never a model-generated conclusion. |

## `backend/app/modules/analysis/data/query_registry.py`（78 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `CompiledQuery`() | 8-11 |  |
| 函数 `compile_business_query(request) -> CompiledQuery` | 65-78 |  |

## `backend/app/modules/analysis/data/query_validation.py`（60 行）

模块说明：Deterministic post-execution evidence checks for controlled SQL.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `assess_query_result(*, columns, rows, contract) -> QueryResultAssessment` | 11-60 | Classify evidence quality; a database success alone is not an answer. |

## `backend/app/modules/analysis/data/sql_candidate.py`（21 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SQLCandidate`(BaseModel) | 5-21 | LLM 为一次经营数据查询生成的候选结果。 |

## `backend/app/modules/analysis/data/sql_executor.py`（189 行）

模块说明：安全的只读SQL执行器

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_apply_row_limit(sql, max_rows) -> str` | 22-36 | Keep a bounded top-level LIMIT or enforce the execution cap. |
| 函数 `_mask_sensitive_rows(rows)` | 39-54 | 对两个只读执行路径使用同一套展示脱敏规则。 |
| 函数 `execute_registered_readonly_query(sql, parameters, *, timeout_ms)` | 57-96 | 执行代码仓库中登记的参数化只读查询，不接受外部 SQL。 |
| 函数 `execute_readonly_sql(sql, allowed_tables, max_rows, timeout_ms, *, catalog, data_source)` | 99-161 | 校验并执行只读SQL，返回 (列名列表, 行数据列表) |
| 类 `_ConnectionDetails`(TypedDict) | 164-169 |  |
| 函数 `_connection_details(data_source) -> _ConnectionDetails` | 172-189 | Resolve a tenant source without persisting or logging its password. |

## `backend/app/modules/analysis/data/sql_generation.py`（422 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_required_concepts_instruction(required_concepts) -> str` | 68-77 |  |
| 函数 `_evaluation_scope_instruction(evaluation_scope) -> str` | 80-90 |  |
| 函数 `hidden_table_names(catalog, shown) -> list[str]` | 93-95 | Allowed tables whose columns are left out of this prompt. |
| 函数 `build_sql_generation_system_prompt(catalog, *, shown_tables) -> str` | 98-182 |  |
| 函数 `_build_snapshot_sql_generation_system_prompt(catalog, shown_tables) -> str` | 185-259 |  |
| 函数 `metric_contract_lines(catalog) -> list[str]` | 262-285 |  |
| 函数 `_catalog_contains_column(catalog, column) -> bool` | 288-290 |  |
| 函数 `sql_context_manifest(question, system_prompt, instructions, previous_sql) -> ContextManifest \| None` | 293-327 | The manifest recorded with one SQL call; enforce refuses one that cannot fit. |
| 类 `SQLGenerationService`() | 330-422 | 调用模型生成候选 SQL，不负责校验或执行 SQL。 |
| 函数 `SQLGenerationService.__init__(gateway, *, catalog) -> None` | 333-340 |  |
| 函数 `SQLGenerationService._tables_for(question, required_concepts, evaluation_scope) -> set[str] \| None` | 342-352 |  |
| 函数 `SQLGenerationService.generate(question, *, repair_reason, previous_sql, required_concepts, evaluation_scope) -> SQLCandidate` | 354-422 |  |

## `backend/app/modules/analysis/data/sql_tool.py`（129 行）

模块说明：SQL 数据查询工具

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SQLTool`(Tool) | 17-129 | 基于只读SQL查询经营数据的工具 |
| 函数 `SQLTool.__init__(*, data_source, snapshot_catalog) -> None` | 20-29 |  |
| 函数 `SQLTool.name() -> str` | 32-33 |  |
| 函数 `SQLTool.description() -> str` | 36-37 |  |
| 函数 `SQLTool.execute(input) -> ToolOutput` | 39-129 |  |

## `backend/app/modules/analysis/data/sql_validator.py`（128 行）

模块说明：Read-only SQL validation with a tenant snapshot table boundary.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `validate_sql(sql, allowed_tables, *, catalog) -> None` | 10-24 | Accept one read-only query and keep every physical table in scope. |
| 函数 `_parse_single_select(sql) -> exp.Select` | 27-44 |  |
| 函数 `_function_names(node) -> set[str]` | 78-82 |  |
| 函数 `_validate_no_side_effects(statement) -> None` | 85-97 |  |
| 函数 `_validate_tables(statement, allowed_tables, catalog) -> None` | 100-128 | Treat CTE names as local aliases; validate every physical table. |

## `backend/app/modules/analysis/data/template_query.py`（60 行）

模块说明：只执行仓库登记查询的经营数据工具。

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `TemplateQueryTool`(Tool) | 10-60 | 把受校验的 query_id 和参数编译为仓库内固定 SQL。 |
| 函数 `TemplateQueryTool.name() -> str` | 14-15 |  |
| 函数 `TemplateQueryTool.description() -> str` | 18-19 |  |
| 函数 `TemplateQueryTool.execute(input) -> ToolOutput` | 21-60 |  |

## `backend/app/modules/analysis/data/tool_agent.py`（571 行）

模块说明：Data Agent whose model chooses its tools inside the same gates as the fixed route.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DescribeTableArgs`(BaseModel) | 66-68 |  |
| 类 `RunSqlArgs`(SQLCandidate) | 71-74 |  |
| 类 `SubmitResultArgs`(BaseModel) | 77-79 |  |
| 类 `ReportInsufficientArgs`(BaseModel) | 82-85 |  |
| 函数 `summarize_rows(columns, rows, *, max_rows) -> dict` | 150-178 | What the model sees of a result; the complete rows stay on the server. |
| 函数 `build_data_tool_prompt(catalog, *, seeded) -> str` | 181-207 |  |
| 函数 `_table_detail(catalog, name) -> dict` | 210-225 |  |
| 函数 `_table_details_block(catalog, tables) -> list[str]` | 228-235 |  |
| 函数 `_contract(candidate) -> QueryContract` | 238-242 | run_sql builds every candidate from RunSqlArgs, which requires a contract. |
| 类 `_DataToolSession`() | 245-485 | One run's handlers and server-side evidence store. |
| 函数 `_DataToolSession.__init__(agent, input) -> None` | 248-263 |  |
| 函数 `_DataToolSession.handlers() -> dict` | 266-272 |  |
| 函数 `_DataToolSession.describe_table(args) -> ToolReply` | 274-288 |  |
| 函数 `_DataToolSession._refuse(code, reason, **details) -> ToolReply` | 290-292 |  |
| 函数 `_DataToolSession._stop(code, reason, sql, purpose) -> ToolReply` | 294-302 |  |
| 函数 `_DataToolSession._gate(candidate, metric_assessment) -> ToolReply \| None` | 304-367 | The fixed route's gates, in the same order. None means all passed. |
| 函数 `_DataToolSession.run_sql(args) -> ToolReply` | 369-387 |  |
| 函数 `_DataToolSession._tool_failure(result) -> ToolReply` | 389-398 |  |
| 函数 `_DataToolSession._tool_success(candidate, result, metric_assessment) -> ToolReply` | 400-449 |  |
| 函数 `_DataToolSession.submit_result(args) -> ToolReply` | 451-460 |  |
| 函数 `_DataToolSession.report_insufficient(args) -> ToolReply` | 462-470 |  |
| 函数 `_DataToolSession.output_for(evidence) -> AgentOutput` | 472-485 | The fixed route's output for this evidence, so routing cannot tell them apart. |
| 类 `ToolCallingDataAgent`(DataAgent) | 488-571 | Same output contract as DataAgent, so the rest of the workflow cannot tell. |
| 函数 `ToolCallingDataAgent.__init__(*args, gateway, seed_schema, limits, **kwargs) -> None` | 491-502 |  |
| 函数 `ToolCallingDataAgent._reviewer() -> SemanticReviewService` | 504-507 |  |
| 函数 `ToolCallingDataAgent._user_prompt(input, session) -> str` | 509-514 |  |
| 函数 `ToolCallingDataAgent._seeded_tables(input, session) -> set[str]` | 516-523 |  |
| 函数 `ToolCallingDataAgent.run(input) -> AgentOutput` | 525-548 |  |
| 函数 `ToolCallingDataAgent._finish(input, session, loop) -> AgentOutput` | 550-571 |  |

## `backend/app/modules/analysis/metrics/claim_validation.py`（53 行）

模块说明：Deterministically classify a bounded numeric claim against query output.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClaimAssessment`() | 10-12 |  |
| 函数 `assess_numeric_assertion(assertion, *, columns, rows, metric_status) -> ClaimAssessment` | 15-53 | Return evidence status; absence or malformed output never becomes support. |

## `backend/app/modules/analysis/metrics/facts.py`（90 行）

模块说明：Deterministically derive facts from controlled data evidence only.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `render_evidence_purpose(purpose) -> str` | 26-28 | Never promote model-generated SQL purpose text into a business fact. |
| 函数 `render_data_fields(columns, row) -> str` | 31-43 |  |
| 函数 `build_data_evidence(data_result) -> list[DataEvidence]` | 46-60 |  |
| 函数 `build_confirmed_facts(data_evidence) -> list[ConfirmedFact]` | 63-90 | No LLM is involved: a fact is a bounded rendering of one result row. |

## `backend/app/modules/analysis/metrics/metric_catalog.py`（155 行）

模块说明：Versioned metric definitions for the managed demonstration business source.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MetricDefinition`() | 15-39 |  |
| 函数 `MetricDefinition.aggregate_display() -> str` | 33-39 |  |
| 函数 `get_metric_definition(reference) -> MetricDefinition \| None` | 152-155 |  |

## `backend/app/modules/analysis/metrics/metric_validation.py`（237 行）

模块说明：Deterministic metric, time, unit, and SQL-lineage validation.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MetricQueryAssessment`() | 18-22 |  |
| 函数 `assess_metric_query(sql, contract, *, evaluation_scope) -> MetricQueryAssessment` | 25-124 | Accept only a declared metric whose technical lineage is visible in SQL. |
| 函数 `_comparison_scope_reason(statement, *, aliases, contract, evaluation_scope) -> str \| None` | 127-167 | Require a frozen two-month scope to appear in the SQL time predicate. |
| 函数 `_next_month(month) -> str` | 170-176 |  |
| 函数 `_canonical_column(column, aliases) -> str` | 179-183 |  |
| 函数 `_canonical_expression(argument, aliases) -> str` | 186-193 |  |
| 函数 `_has_required_equality(statement, aliases, expected_column, expected_value) -> bool` | 196-212 |  |
| 函数 `_has_required_aggregate(statement, aliases, definition) -> bool` | 215-237 |  |

## `backend/app/modules/analysis/planner/facts.py`（161 行）

模块说明：What code can see in a question before any model runs (B2c: recorded, not used).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `QuestionFacts`() | 99-122 |  |
| 函数 `QuestionFacts.event_details() -> dict` | 109-122 | Dates and flags only; the question text never enters the event. |
| 函数 `_mentions(question, words) -> bool` | 125-126 |  |
| 函数 `_month(year, month) -> tuple[date, date]` | 129-130 |  |
| 函数 `_asks_business_metric(question, *, asks_quantity, is_comparison) -> bool` | 133-139 |  |
| 函数 `extract_question_facts(question, today) -> QuestionFacts` | 142-161 |  |

## `backend/app/modules/analysis/planner/plan_schemas.py`（37 行）

模块说明：Planner Agent 的受控输出契约。

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisPlan`(BaseModel) | 15-37 | 决定工作流的执行路径。 |
| 函数 `AnalysisPlan.route_matches_requested_sources() -> 'AnalysisPlan'` | 26-37 |  |

## `backend/app/modules/analysis/planner/planner_agent.py`（98 行）

模块说明：Planner Agent —— 调用 LLM 生成受校验的工作流决策。

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `PlannerAgent`(Agent) | 19-98 | 调用 LLM 生成工作流决策，但不生成最终业务结论。 |
| 函数 `PlannerAgent.__init__(planning_service) -> None` | 22-23 |  |
| 函数 `PlannerAgent.name() -> str` | 26-27 |  |
| 函数 `PlannerAgent.description() -> str` | 30-31 |  |
| 函数 `PlannerAgent.allowed_tools() -> list[Tool]` | 34-35 |  |
| 函数 `PlannerAgent.run(input) -> AgentOutput` | 37-98 |  |

## `backend/app/modules/analysis/planner/planner_decision.py`（182 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `EvaluationScope`(BaseModel) | 35-39 | The Planner's structured interpretation, not a business fact. |
| 函数 `enforce_explicit_document_evidence_contract(question, decision) -> 'PlannerDecision'` | 42-74 | Keep document-only questions narrow, but preserve explicit data-plus-doc work. |
| 类 `PlannerDecision`(BaseModel) | 77-182 |  |
| 函数 `PlannerDecision.validate_action_contract() -> 'PlannerDecision'` | 134-182 |  |

## `backend/app/modules/analysis/planner/planning.py`（559 行）

模块说明：LLM Planner service: classify a question into a validated workflow decision.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_max_planner_attempts() -> int` | 33-34 |  |
| 函数 `_canonical_symmetric_month_scope(question, decision) -> PlannerDecision` | 53-83 | Canonicalize only an explicitly symmetric two-month comparison scope. |
| 函数 `build_planning_system_prompt() -> str` | 86-88 | Return the immutable policy for one structured planning decision. |
| 函数 `_standing_constraints_note(conversation_context) -> str` | 91-99 | Only when there are some, so every other prompt stays exactly as it was. |
| 函数 `_conversation_state_note(conversation_context) -> str` | 102-122 | Only with a conversation state (C6), so every other prompt stays as it was. |
| 函数 `_history_summary_block(history_summary) -> str` | 125-145 | Only with a summary (C9c), so every other prompt stays as it was. |
| 函数 `build_planning_user_prompt(question, conversation_context, feedback, planner_memory, retry_context, attachment_context, history_summary) -> str` | 148-195 |  |
| 类 `PlannerInputs`(NamedTuple) | 198-204 |  |
| 函数 `context_too_long_decision() -> PlannerDecision` | 218-230 | Asked back without calling the model: nothing is reserved or charged. |
| 函数 `planner_context(question, inputs) -> tuple[PlannerInputs, ContextManifest \| None]` | 233-272 | The prompt inputs to send and the manifest the ledger records with them (C4). |
| 函数 `build_planning_repair_prompt(question, conversation_context, raw_output, error, feedback, planner_memory, retry_context, attachment_context, history_summary) -> str` | 275-373 | Ask the model to repair its specific contract violation without exposing it to users. |
| 类 `PlanningService`() | 376-559 | Call the configured model and validate its workflow decision. |
| 函数 `PlanningService.__init__(gateway, sleeper) -> None` | 379-386 |  |
| 函数 `PlanningService.decide(question, *, conversation_context, feedback, planner_memory, retry_context, attachment_context, history_summary) -> PlannerDecision` | 388-559 |  |

## `backend/app/modules/analysis/planner/rules.py`（117 行）

模块说明：Plan rules over QuestionFacts (B2d: shadow, recorded beside the Planner's plan).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `PlanRule`() | 19-23 |  |
| 函数 `_has_time(facts) -> bool` | 26-27 |  |
| 函数 `_document_only(facts) -> bool` | 32-33 |  |
| 函数 `_document_and_metric(facts) -> bool` | 36-37 |  |
| 函数 `_number_without_time(facts) -> bool` | 40-42 |  |
| 函数 `_comparison_without_time(facts) -> bool` | 45-47 |  |
| 函数 `plan_label(plan) -> str \| None` | 58-61 |  |
| 函数 `matching_rules(facts) -> list[PlanRule]` | 64-65 |  |
| 函数 `arbitrate(hits) -> str \| None` | 77-88 | The decision the hits make together, or None to leave it to the Planner. |
| 函数 `rule_question(original, plan) -> tuple[str, str]` | 91-96 | The question the rules read, and "resolved" or "original" for the record. |
| 函数 `shadow_details(facts, plan) -> dict` | 99-117 | Rule ids and labels only; like the facts event, no question text. |

## `backend/app/modules/analysis/tool_protocol.py`（46 行）

模块说明：工具协议 —— 所有工具必须实现这个接口

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ToolInput`() | 9-12 | 一次工具调用的输入 |
| 类 `ToolOutput`() | 16-25 | 一次工具调用的输出 |
| 类 `Tool`(ABC) | 28-46 | 工具基类 —— 所有工具必须实现下面这些属性和方法 |
| 函数 `Tool.name() -> str` | 33-35 | 工具名称，如 'rag_search'、'sql_query' |
| 函数 `Tool.description() -> str` | 39-41 | 工具描述，告诉Agent这个工具能干什么 |
| 函数 `Tool.execute(input) -> ToolOutput` | 44-46 | 执行工具，输入参数，返回结果 |

## `backend/app/modules/conversations/api.py`（351 行）

模块说明：Conversation HTTP API.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_task_observability(db, task) -> dict` | 48-104 |  |
| 函数 `_conversation_task_out(db, task) -> ConversationTaskOut` | 107-140 |  |
| 函数 `create_conversation_endpoint(request_model, context, db)` | 148-163 |  |
| 函数 `list_conversations_endpoint(context, db)` | 167-171 |  |
| 函数 `get_conversation_endpoint(conversation_id, context, db)` | 175-187 |  |
| 函数 `list_conversation_messages_endpoint(conversation_id, context, db)` | 194-206 |  |
| 函数 `get_conversation_task_endpoint(conversation_id, task_id, context, db)` | 213-227 |  |
| 函数 `cancel_conversation_task_endpoint(conversation_id, task_id, context, db)` | 234-251 |  |
| 函数 `retry_conversation_task_endpoint(conversation_id, task_id, request, context, db)` | 259-298 |  |
| 函数 `create_conversation_message_endpoint(conversation_id, request_model, request, context, db)` | 306-351 |  |

## `backend/app/modules/conversations/models.py`（150 行）

模块说明：Conversation and display-message persistence models.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Conversation`(Base) | 13-44 |  |
| 类 `ConversationMessage`(Base) | 47-91 |  |
| 类 `ConversationState`(Base) | 94-120 | Standing constraints and current subject of one conversation (C6). |
| 类 `ConversationSummary`(Base) | 123-150 | What the messages that left the context window said (C9). |

## `backend/app/modules/conversations/repository.py`（153 行）

模块说明：Database operations for conversations and their display messages.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `create_conversation(db, *, user_id, title, company_id, data_source_id) -> Conversation` | 8-24 |  |
| 函数 `get_conversation_by_id(db, *, conversation_id, user_id, company_id) -> Conversation \| None` | 27-42 |  |
| 函数 `get_conversations(db, *, user_id, company_id) -> list[Conversation]` | 45-53 |  |
| 函数 `create_message(db, *, conversation_id, role, content, status, analysis_task_id) -> ConversationMessage` | 56-74 |  |
| 函数 `get_messages(db, *, conversation_id) -> list[ConversationMessage]` | 77-87 |  |
| 函数 `get_assistant_message_by_task_id(db, *, task_id) -> ConversationMessage \| None` | 90-102 |  |
| 函数 `touch_conversation(db, *, conversation_id) -> None` | 105-109 |  |
| 函数 `get_older_user_messages(db, *, conversation_id, before_message_id, limit) -> list[ConversationMessage]` | 112-131 |  |
| 函数 `get_recent_context_messages(db, *, conversation_id, before_message_id, limit) -> list[ConversationMessage]` | 134-153 |  |

## `backend/app/modules/conversations/schemas.py`（84 行）

模块说明：Public request and response contracts for conversations.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConversationCreate`(BaseModel) | 20-24 |  |
| 类 `ConversationMessageCreate`(BaseModel) | 27-46 |  |
| 函数 `ConversationMessageCreate.validate_artifact_version_ids(value) -> list[int]` | 36-46 |  |
| 类 `ConversationOut`(BaseModel) | 49-58 |  |
| 类 `ConversationMessageOut`(BaseModel) | 61-71 |  |
| 类 `ConversationMessageAccepted`(BaseModel) | 74-78 |  |
| 类 `ConversationTaskRetryAccepted`(BaseModel) | 81-84 |  |

## `backend/app/modules/conversations/service.py`（678 行）

模块说明：Transactional orchestration for conversation APIs.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConversationTaskBundle`() | 47-51 |  |
| 类 `ConversationTaskRetryBundle`() | 55-58 |  |
| 类 `ConversationDocumentScopeError`(ValueError) | 61-62 | A requested document is not readable in the current company role. |
| 类 `ConversationInputArtifactScopeError`(ValueError) | 65-66 | An attachment is unavailable, not ready, or not owned by the actor. |
| 类 `DataSourceNotReadyError`(ValueError) | 69-70 | A conversation cannot run without an activated schema snapshot. |
| 函数 `create_conversation_service(db, *, context, title, data_source_id) -> Conversation` | 73-104 |  |
| 函数 `get_conversation_service(db, *, conversation_id, context) -> Conversation \| None` | 107-118 |  |
| 函数 `get_conversations_service(db, *, context) -> list[Conversation]` | 121-124 |  |
| 函数 `get_conversation_messages_service(db, *, conversation_id, context) -> list[ConversationMessage] \| None` | 127-140 |  |
| 函数 `get_conversation_task_service(db, *, conversation_id, task_id, context) -> AnalysisTask \| None` | 143-161 | Return a task only through its owning current-company conversation. |
| 函数 `create_conversation_task_service(db, *, conversation_id, context, content, document_ids, artifact_version_ids, request_id) -> ConversationTaskBundle \| None` | 167-305 |  |
| 函数 `cancel_conversation_task_service(db, *, conversation_id, task_id, context, request_id) -> AnalysisTask \| None` | 308-341 | Cancel a non-terminal conversation task and update its assistant message. |
| 函数 `retry_conversation_task_service(db, *, conversation_id, task_id, context, request_id) -> ConversationTaskRetryBundle \| None` | 344-411 | Create a linked retry without mutating the original terminal task. |
| 函数 `_resolve_ready_owned_artifact_version_ids(db, *, context, artifact_version_ids) -> list[int]` | 414-442 |  |
| 函数 `find_standing_constraints(messages) -> list[dict]` | 458-472 | Requests from messages too old to fit the history, newest kept first. |
| 函数 `estimate_conversation_tokens(text) -> int` | 475-477 | Use the configured-family tokenizer for deterministic history selection. |
| 函数 `_token_limited_prefix(content, max_tokens) -> str` | 480-489 | Return the longest character prefix that fits the history token budget. |
| 函数 `build_conversation_context(messages, *, max_chars, max_message_chars, min_fragment_chars, max_tokens, max_messages) -> dict` | 492-678 |  |

## `backend/app/modules/conversations/state.py`（107 行）

模块说明：Read and write a conversation's structured state (C6).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `empty_state() -> dict` | 26-32 |  |
| 类 `LoadedState`() | 36-39 |  |
| 函数 `load_state(db, conversation_id) -> LoadedState` | 42-50 |  |
| 函数 `freeze_state(db, *, conversation_id, message_id) -> dict` | 53-57 | What a new task's snapshot keeps (M7): the state as of now, its version |
| 函数 `save_state(db, *, conversation_id, company_id, state, expected_version, task_id) -> bool` | 60-107 | Write the state if nobody changed it since ``expected_version`` was read. |

## `backend/app/modules/conversations/state_extractor.py`（106 行）

模块说明：Ask the model which standing scope the current user message sets (C6f).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Extraction`() | 38-40 |  |
| 函数 `_as_dict(message) -> dict` | 43-44 |  |
| 函数 `render_prompt(payload) -> str` | 47-60 | The user prompt, from what the policy let through. |
| 函数 `parse_output(raw) -> Extraction` | 63-72 | Keep the object items of ``state_update``; anything else proposes nothing. |
| 函数 `extract_state_update(gateway, *, state, history, current) -> Extraction` | 75-106 | Proposals for ``current``; ``history`` is the messages before it. |

## `backend/app/modules/conversations/state_update.py`（110 行）

模块说明：How a Planner proposal becomes the next conversation state (C6b).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Message`(Protocol) | 39-42 |  |
| 函数 `apply_update(state, updates, messages) -> tuple[dict, list[dict]]` | 45-104 | Return (new state, rejected items); ``state`` itself is never changed. |
| 函数 `set_subject(state, entities, period) -> dict` | 107-110 | The subject the next "this region" refers to: the last analysis's scope. |

## `backend/app/modules/conversations/summarizer.py`（98 行）

模块说明：Ask the model to merge messages that left the window into the summary (C9).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Summarization`() | 33-35 |  |
| 函数 `_as_dict(message) -> dict` | 38-39 |  |
| 函数 `render_prompt(payload) -> str` | 42-54 | The user prompt, from what the policy let through. |
| 函数 `parse_output(raw) -> Summarization` | 57-69 | Keep the object items of ``summary_items``; anything else proposes nothing. |
| 函数 `summarize(gateway, *, summary, messages) -> Summarization` | 72-98 | The new item list for ``summary`` after ``messages`` left the window. |

## `backend/app/modules/conversations/summary.py`（101 行）

模块说明：Read and write a conversation's summary of earlier messages (C9).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `empty_summary() -> dict` | 26-34 |  |
| 类 `LoadedSummary`() | 38-41 |  |
| 函数 `load_summary(db, conversation_id) -> LoadedSummary` | 44-52 |  |
| 函数 `save_summary(db, *, conversation_id, company_id, summary, expected_version, task_id) -> bool` | 55-101 | Write the summary if nobody changed it since ``expected_version`` was read. |

## `backend/app/modules/conversations/summary_update.py`（145 行）

模块说明：Decide which proposed summary items are kept (C9).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `apply_summary(summary, items, messages, *, window_start_id) -> tuple[dict, list[dict]]` | 25-64 | Return (new summary, rejected items); ``summary`` itself is never changed. |
| 函数 `_reject_reason(item, by_id, window_start_id) -> str \| None` | 67-97 | The first check ``item`` fails, or None when it may be kept. |
| 函数 `window_start(messages, *, window_size) -> int \| None` | 100-115 | The id of the oldest message the next task still sees, or None. |
| 函数 `messages_to_summarize(messages, *, covered_through, window_start_id, limit) -> list[Message]` | 118-132 | The oldest ``limit`` messages with content that are newer than |
| 函数 `planner_summary(summary, *, window_start_id) -> list[str]` | 135-145 | The texts the Planner may read, in item order. |

## `backend/app/modules/documents/api.py`（201 行）

模块说明：Documents are always scoped by the authenticated user's only company.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `list_documents(context, db)` | 40-44 |  |
| 函数 `_validate_requested_visibility(context, role) -> None` | 47-56 |  |
| 函数 `create_document(request, context, db)` | 64-83 |  |
| 函数 `_document_or_404(db, context, document_id)` | 86-92 |  |
| 函数 `get_document(document_id, context, db)` | 96-101 |  |
| 函数 `delete_document(document_id, context, db)` | 105-119 |  |
| 函数 `update_document(document_id, request, context, db)` | 127-154 |  |
| 异步函数 `upload_document(file, context, db)` | 162-191 |  |
| 函数 `get_document_chunks(document_id, context, db)` | 195-201 |  |

## `backend/app/modules/documents/chunk_repository.py`（49 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `add_chunk(db, *, document_id, company_id, chunk_strategy, chunk_index, content, token_count, embedding, page_number, paragraph_start, paragraph_end) -> DocumentChunk` | 6-35 |  |
| 函数 `get_chunks_by_document_id(db, document_id) -> list[DocumentChunk]` | 38-49 |  |

## `backend/app/modules/documents/chunk_schemas.py`（15 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ChunkOut`(BaseModel) | 6-15 |  |

## `backend/app/modules/documents/chunks.py`（60 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DocumentChunk`(Base) | 18-60 |  |

## `backend/app/modules/documents/ingestion.py`（164 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `upload_document_service(db, *, uploaded_by_user_id, company_id, file_stream, original_name, settings) -> Documents` | 27-70 |  |
| 函数 `passage_records(content, fallback) -> list[ChunkText]` | 73-79 | Passages for one document; never empty when the document has text. |
| 函数 `process_document_chunks(db, document, settings) -> Documents` | 82-164 |  |

## `backend/app/modules/documents/models.py`（93 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Documents`(Base) | 19-93 |  |

## `backend/app/modules/documents/repository.py`（177 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `allowed_min_view_roles(role) -> tuple[str, ...]` | 6-11 |  |
| 函数 `save_document(db, uploaded_by_user_id, name, content, source, company_id, min_view_role)` | 14-35 |  |
| 函数 `get_document(db, company_id, role)` | 38-51 |  |
| 函数 `get_document_by_id(db, document_id, company_id, role)` | 54-63 |  |
| 函数 `get_document_for_mutation(db, *, document_id, company_id, role, actor_user_id)` | 66-81 |  |
| 函数 `delete_document(db, document_id, company_id, role, actor_user_id)` | 84-103 |  |
| 函数 `update_document(db, document_id, name, content, source, company_id, role, actor_user_id, min_view_role)` | 106-139 |  |
| 函数 `get_document_by_sha256(db, sha256, company_id) -> Documents \| None` | 142-148 |  |
| 函数 `add_uploaded_document(db, *, uploaded_by_user_id, company_id, name, file_path, file_type, file_size, sha256) -> Documents` | 151-177 |  |

## `backend/app/modules/documents/schemas.py`（40 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DocumentCreate`(BaseModel) | 10-14 |  |
| 类 `DocumentUpdate`(BaseModel) | 17-21 |  |
| 类 `DocumentOut`(BaseModel) | 24-40 |  |

## `backend/app/modules/documents/search_tokens.py`（70 行）

模块说明：Turn Chinese text into the words PostgreSQL full-text search will index.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `jieba_tokens(text) -> list[str]` | 41-49 | Words for the search index; a long word also yields its parts. |
| 函数 `bigram_tokens(text) -> list[str]` | 52-59 | Overlapping two-character pieces; the comparison baseline for jieba. |
| 函数 `search_vector_expression(text, tokenizer)` | 68-70 | SQL expression storing the text's tokens as a tsvector. |

## `backend/app/modules/documents/service.py`（93 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `save_document_service(db, uploaded_by_user_id, name, content, source, company_id, min_view_role) -> Documents` | 12-29 |  |
| 函数 `get_document_service(db, company_id, role) -> list[Documents]` | 32-33 |  |
| 函数 `get_document_by_id_service(db, document_id, company_id, role)` | 36-44 |  |
| 函数 `delete_document_service(db, document_id, company_id, role, actor_user_id)` | 47-64 |  |
| 函数 `update_document_service(db, document_id, name, content, source, company_id, role, actor_user_id, min_view_role)` | 67-93 |  |

## `backend/app/modules/documents/storage.py`（111 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `StoredDocumentFile`() | 19-26 |  |
| 函数 `_validate_document_name(original_name, allowed_extensions) -> tuple[str, str]` | 29-47 |  |
| 函数 `save_document_file(file_stream, original_name, settings) -> StoredDocumentFile` | 50-111 |  |

## `backend/app/modules/documents/tasks.py`（58 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `process_document_task(document_id, company_id) -> None` | 14-58 | 异步切分文档并生成、保存 Embedding。 |

## `backend/app/modules/documents/vector_repository.py`（219 行）

模块说明：向量搜索 Repository

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_character_bigrams(text_value) -> set[str]` | 17-19 |  |
| 函数 `_hybrid_score(question, content, vector_score) -> float` | 22-26 |  |
| 函数 `_scope_filter(document_ids) -> str` | 29-30 |  |
| 函数 `_validity_filter(valid_between) -> str` | 33-37 |  |
| 函数 `search_similar_chunks(db, embedding, company_id, question, top_k, min_score, document_ids, chunk_strategy, valid_between) -> list[dict]` | 40-131 | 搜索与给定向量最相似的文档分块 |
| 函数 `search_keyword_chunks(db, tokens, embedding, company_id, top_k, document_ids, chunk_strategy, valid_between) -> list[dict]` | 134-211 | 全文检索：任一词命中即入选，按相关度排序；过滤条件与向量检索相同。 |
| 函数 `delete_embeddings_by_document(db, document_id) -> None` | 214-219 | 删除文档的所有向量（删除文档时同步调用） |

## `backend/app/modules/documents/versioning.py`（67 行）

模块说明：Register a document as one version of a group and retire what it replaces.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_dated(document) -> tuple[int, date]` | 10-14 | Every member of a version group was registered with a number and a date. |
| 函数 `register_document_version(db, *, document, version_group, version_number, effective_from, effective_to, document_kind, applies_to) -> None` | 17-67 | Link the document to its neighbours so no two versions overlap in time. |

## `backend/app/modules/evaluation/business.py`（894 行）

模块说明：Deterministic evaluator for persisted Worker observations, not an LLM judge.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_canonical_entity_scope(value) -> str` | 22-26 |  |
| 函数 `_contains_all(expected, actual) -> bool` | 29-31 |  |
| 函数 `_term_is_negated(item, start) -> bool` | 56-74 | Reject a literal or approved variant when its preceding clause negates it. |
| 函数 `_contains_document_term(term, item) -> bool` | 77-85 |  |
| 函数 `_contains_required_terms(expected, actual, *, reject_negated_claims) -> bool` | 88-106 | Require every term group in one returned item without using an LLM judge. |
| 函数 `_p95_duration(observations, attribute) -> int \| None` | 109-117 |  |
| 函数 `_and_status(statuses) -> CheckStatus` | 120-125 |  |
| 函数 `_is_sha256_result_fingerprint(value) -> bool` | 136-142 |  |
| 函数 `_security_rejection_result(case, observation) -> EvaluationCaseResult` | 145-195 | Evaluate a denied operation without requiring a business report. |
| 函数 `_runtime_tool_rejection_result(case, observation) -> EvaluationCaseResult` | 198-255 | Evaluate a durable Runtime denial without treating it as an HTTP rejection. |
| 函数 `_sql_validation_rejection_result(case, observation) -> EvaluationCaseResult` | 258-315 | Evaluate a persisted SQL validation failure without calling it a denial. |
| 函数 `_sql_result_limit_result(case, observation) -> EvaluationCaseResult` | 318-373 |  |
| 函数 `_sql_timeout_result(case, observation) -> EvaluationCaseResult` | 376-431 | Evaluate a persisted SQL timeout without calling it a validation denial. |
| 函数 `_duplicate_delivery_result(case, observation) -> EvaluationCaseResult` | 434-491 | Evaluate one rejected duplicate claim and a preserved single execution. |
| 函数 `_execution_fence_result(case, observation) -> EvaluationCaseResult` | 494-551 | Evaluate a persisted stale-write fence without calling it a tool denial. |
| 函数 `_clarification_result(case, observation) -> EvaluationCaseResult` | 554-615 | Evaluate a pre-analysis clarification without treating it as a report. |
| 函数 `evaluate_case(case, observation) -> EvaluationCaseResult` | 618-799 |  |
| 函数 `_rate(results, field, *, kind) -> float \| None` | 802-819 |  |
| 函数 `evaluate_run(cases, observations) -> tuple[list[EvaluationCaseResult], EvaluationMetrics]` | 822-894 |  |

## `backend/app/modules/evaluation/business_schemas.py`（493 行）

模块说明：Versioned, deterministic contracts for business-analysis evaluation.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RequiredTerms`(BaseModel) | 47-62 | A deterministic, wording-tolerant expectation for one reported item. |
| 函数 `RequiredTerms.terms_are_nonempty_and_distinct(value) -> list[str]` | 56-62 |  |
| 类 `EvaluationCase`(BaseModel) | 65-317 | One immutable business outcome contract; no answer key is sent to the Agent. |
| 函数 `EvaluationCase.semantic_result_fingerprint_is_sha256(value) -> dict[str, str] \| None` | 124-135 |  |
| 函数 `EvaluationCase.validates_route_specific_inapplicable_gates() -> 'EvaluationCase'` | 138-317 |  |
| 类 `EvaluationFixture`(BaseModel) | 320-325 |  |
| 类 `EvaluationObservation`(BaseModel) | 328-404 | Normalized result facts with an explicit real or simulated source. |
| 类 `EvaluationCaseResult`(BaseModel) | 407-443 |  |
| 类 `EvaluationMetrics`(BaseModel) | 446-472 |  |
| 类 `EvaluationRun`(BaseModel) | 475-493 | Portable JSON artifact; filesystem persistence avoids an evaluation migration. |

## `backend/app/modules/evaluation/memory_selection.py`（34 行）

模块说明：Score which memories a selector hands to the model for each question.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `score_memory_case(*, selected, must_select, must_not_select) -> dict` | 8-18 |  |
| 函数 `summarize_memory_cases(rows) -> dict` | 21-34 |  |

## `backend/app/modules/evaluation/observation.py`（998 行）

模块说明：Normalize persisted task facts into a business-evaluation observation.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_execution_timing_ms(db, *, task) -> int \| None` | 43-66 | Sum completed Worker ownership intervals; queue and review wait are excluded. |
| 函数 `_human_review_wait_ms(db, *, task) -> int \| None` | 69-78 | Read a decision wait only when the durable review timestamps are complete. |
| 函数 `_check_status(value) -> CheckStatus` | 81-86 |  |
| 函数 `_persisted_entities(value) -> list[str] \| None` | 89-96 |  |
| 函数 `_persisted_period(value) -> str \| None` | 99-100 |  |
| 函数 `_persisted_data_status(value) -> str \| None` | 103-109 |  |
| 函数 `_persisted_data_error_code(value) -> str \| None` | 112-117 |  |
| 函数 `_persisted_clarification_missing_fields(value) -> list[ClarificationSlot] \| None` | 120-126 |  |
| 函数 `_status_or_none(value) -> str \| None` | 129-130 |  |
| 函数 `_list_count_or_none(value) -> int \| None` | 133-134 |  |
| 函数 `_persisted_result_fingerprint(value) -> dict[str, str] \| None` | 137-145 |  |
| 函数 `_citation_document_paths(db, *, task, report) -> list[str] \| None` | 148-194 |  |
| 函数 `_citation_security_status(db, *, task, report) -> CheckStatus` | 197-222 |  |
| 函数 `_answer_path(calls) -> list[ModelCallRecord]` | 225-232 | The calls a case's call and token limits apply to (M7c, C9). |
| 函数 `_model_cost_observation(calls) -> tuple[str \| None, CheckStatus]` | 235-244 | Return a total only when every durable model charge is settled. |
| 函数 `observation_from_persisted_task(db, *, case_id, task_id) -> EvaluationObservation` | 247-439 | Read one terminal task and its model-call ledger without inventing facts. |
| 函数 `observation_from_request_rejection(db, *, case_id, company_id, request_id) -> EvaluationObservation` | 442-473 | Read a persisted rejection and prove that it created no scoped task. |
| 函数 `observation_from_runtime_tool_rejection(db, *, case_id, task_id) -> EvaluationObservation` | 476-550 | Read a persisted Runtime denial and prove its tool never executed. |
| 函数 `observation_from_sql_validation_rejection(db, *, case_id, task_id) -> EvaluationObservation` | 553-635 | Read a persisted SQL validation failure and its lack of business result. |
| 函数 `observation_from_sql_result_limit(db, *, case_id, task_id) -> EvaluationObservation` | 638-717 | Read one terminal SQL call and its persisted privacy-safe row count. |
| 函数 `observation_from_sql_timeout(db, *, case_id, task_id) -> EvaluationObservation` | 720-806 | Read one persisted SQL timeout and prove it produced no business result. |
| 函数 `observation_from_duplicate_delivery(db, *, case_id, task_id) -> EvaluationObservation` | 809-893 | Read a rejected duplicate claim and the resulting one-attempt terminal task. |
| 函数 `observation_from_execution_fence(db, *, case_id, task_id) -> EvaluationObservation` | 896-998 | Read a persisted cancellation and rejected stale terminal write. |

## `backend/app/modules/evaluation/report_gate.py`（190 行）

模块说明：Deterministic report-gate evaluation: tampered variants must be blocked, controls kept.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `base_report() -> dict` | 20-55 |  |
| 函数 `_mutate(change) -> dict` | 58-61 |  |
| 类 `GateOutcome`() | 134-142 |  |
| 函数 `GateOutcome.correct() -> bool` | 141-142 |  |
| 函数 `_report_blocked(report, expected_reason) -> bool` | 145-150 |  |
| 函数 `run_report_gate_evaluation() -> dict` | 153-190 |  |

## `backend/app/modules/evaluation/result_fingerprint.py`（196 行）

模块说明：Build a stable fingerprint from validated SQL result evidence.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_canonical_columns(item, columns) -> list[str]` | 16-28 | Keep a validated one-metric result stable when its SQL alias varies. |
| 函数 `result_fingerprint_from_data_result(data_result) -> dict[str, str] \| None` | 31-88 | Return a SHA-256 fingerprint, or ``None`` when no result is provable. |
| 函数 `revenue_month_comparison_fingerprint_from_data_result(data_result, *, period) -> dict[str, str] \| None` | 91-155 | Hash one validated two-month ``revenue/v1`` result, or fail closed. |
| 函数 `_comparison_months(period) -> tuple[str, str] \| None` | 158-165 |  |
| 函数 `_is_supported_revenue_evidence(item) -> bool` | 168-174 |  |
| 函数 `_canonical_month(value) -> str \| None` | 177-181 |  |
| 函数 `_canonical_revenue(value) -> str \| None` | 184-196 |  |

## `backend/app/modules/evaluation/retrieval.py`（173 行）

模块说明：Deterministic metrics for a fixed, permission-safe retrieval evaluation set.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RetrievalEvaluationCase`() | 7-13 |  |
| 类 `RetrievalEvaluationMetrics`() | 17-23 |  |
| 函数 `evaluate_retrieval(cases) -> RetrievalEvaluationMetrics` | 26-63 | Score retrieval output without inferring any business facts or quality claims. |
| 类 `RankedRetrievalCase`() | 67-73 | One question with document-level relevance and the ranked document ids returned. |
| 函数 `_dedupe(ids) -> list[int]` | 76-78 |  |
| 函数 `_aggregate(cases, ks) -> dict` | 81-98 |  |
| 函数 `evaluate_ranked_retrieval(cases, *, ks) -> dict` | 101-124 | Hit@k, Recall@k and MRR at document level, overall and per split. |
| 函数 `answer_hit_rates(rows) -> dict` | 127-141 | Share of questions whose answer text appears in a final retrieved chunk. |
| 函数 `score_version_traps(rows) -> dict` | 144-173 | How often retrieval hands the model a version that does not apply. |

## `backend/app/modules/evaluation/sql_results.py`（118 行）

模块说明：Score generated-SQL results against a hand-written reference result.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_number(value) -> str \| None` | 19-28 |  |
| 函数 `_row_values(row, *, compare_text) -> Counter` | 31-41 |  |
| 函数 `_is_no_data(rows) -> bool` | 44-45 |  |
| 函数 `_matches(reference, actual, *, ordered) -> bool` | 48-59 |  |
| 函数 `score_result(*, expect, agent_success, actual_rows, reference_rows, ordered, compare_text, error_code) -> str` | 62-96 | Return one verdict for a case; ``PASSING_VERDICTS`` lists those that pass. |
| 函数 `summarize(results) -> dict` | 99-118 |  |

## `backend/app/modules/evaluation/support_check.py`（87 行）

模块说明：Score the sentence support check against hand-labelled sentences.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_without_separators(text) -> str` | 16-17 |  |
| 函数 `answer_matches_loosely(expected, answer) -> bool` | 20-34 | Whether the answer states the expected text, however it is spaced. |
| 函数 `summarize_support_cases(rows) -> dict` | 37-57 | citation_support_rate: of the sentences kept, how many deserved it. |
| 函数 `summarize_end_to_end(rows) -> dict` | 60-75 | Effect on real answers: right answers must survive, stale ones must not. |
| 函数 `summarize_loose_answers(rows) -> dict` | 78-87 | The second score, and which answers only it accepts, so they can be read. |

## `backend/app/modules/evaluation/thresholds.py`（173 行）

模块说明：Frozen, deterministic admission checks for a business-evaluation run.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `EvaluationThresholdContract`(BaseModel) | 17-77 | Thresholds that must be fixed before collecting the selected run. |
| 函数 `EvaluationThresholdContract.fixture_sha256_is_lowercase(value) -> str` | 42-45 |  |
| 函数 `EvaluationThresholdContract.baseline_comparison_is_complete() -> EvaluationThresholdContract` | 48-77 |  |
| 函数 `evaluate_threshold_contract(contract, *, fixture_bytes, cases, observations, metrics, baseline_metrics, baseline_run_sha256) -> list[str]` | 80-173 | Return deterministic violations; an empty list is the only pass state. |

## `backend/app/modules/evaluation/tool_selection.py`（59 行）

模块说明：Score which tools a strategy would call for each question.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `tools_for_decision(decision) -> frozenset[str] \| None` | 18-20 | Tools the fixed route would call; ``None`` when the decision is unknown. |
| 函数 `score_tool_case(*, called, acceptable, forbidden) -> dict` | 23-40 |  |
| 函数 `summarize_tool_cases(rows) -> dict` | 43-59 |  |

## `backend/app/modules/evaluation/workflow.py`（55 行）

模块说明：Evaluate durable workflow outcomes for a single company.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_percentile(values, percentile) -> int \| None` | 12-16 |  |
| 函数 `evaluate_company_workflows(db, *, company_id) -> WorkflowEvaluation` | 19-55 |  |

## `backend/app/modules/evaluation/workflow_schemas.py`（15 行）

模块说明：Persisted workflow-level evaluation result, not an in-memory graph assertion.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `WorkflowEvaluation`(BaseModel) | 6-15 |  |

## `backend/app/modules/identity/api.py`（190 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `bootstrap_owner(request, db) -> AccessTokenOut` | 41-57 |  |
| 函数 `login(request, db) -> AccessTokenOut` | 61-68 |  |
| 函数 `read_current_user(context) -> CurrentUserOut` | 72-85 |  |
| 函数 `update_current_user(request, context, db) -> CurrentUserOut` | 89-97 |  |
| 函数 `change_password(request, current_user, db) -> None` | 101-110 |  |
| 函数 `set_initial_password(request, account, db) -> None` | 114-128 | One-time API-key migration path for existing local accounts. |
| 函数 `logout(current_user, db) -> None` | 132-138 | Invalidate every currently issued browser token for this account. |
| 函数 `register_application(request, db) -> MembershipApplicationRegistered` | 146-170 |  |
| 函数 `reapply_application(request, db) -> MembershipApplicationOut` | 177-190 |  |

## `backend/app/modules/identity/authentication.py`（79 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `create_access_token(*, user) -> tuple[str, int]` | 12-27 |  |
| 函数 `_get_bearer_user(authorization, db) -> User \| None` | 30-52 |  |
| 异步函数 `get_authenticated_account(authorization, x_api_key, db) -> User` | 55-71 | Authenticate a browser JWT, with temporary API-key compatibility. |
| 异步函数 `get_current_user(user) -> User` | 74-79 |  |

## `backend/app/modules/identity/models.py`（44 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `User`(Base) | 9-44 |  |
| 函数 `User.api_key() -> str \| None` | 33-39 | Compatibility helper for newly-created test and bootstrap users. |
| 函数 `User.api_key(value) -> None` | 42-44 |  |

## `backend/app/modules/identity/schemas.py`（58 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `UserOut`(BaseModel) | 6-14 |  |
| 类 `CurrentUserOut`(UserOut) | 17-22 | The only post-login identity payload needed by the client. |
| 类 `LoginRequest`(BaseModel) | 25-29 |  |
| 类 `AccessTokenOut`(BaseModel) | 32-35 |  |
| 类 `CurrentUserUpdate`(BaseModel) | 38-41 |  |
| 类 `PasswordChangeRequest`(BaseModel) | 44-46 |  |
| 类 `InitialPasswordSetup`(BaseModel) | 49-53 |  |
| 类 `OwnerBootstrapRequest`(LoginRequest) | 56-58 |  |

## `backend/app/modules/input_artifacts/api.py`（399 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_error_response(*, status_code, code, message) -> JSONResponse` | 74-83 |  |
| 函数 `_build_upload_response(db, *, context, upload_request) -> InputArtifactUploadOut` | 86-119 |  |
| 函数 `_build_upload_session_response(outcome) -> AttachmentUploadSessionOut` | 122-142 |  |
| 函数 `_build_upload_session_completion_response(db, *, context, outcome) -> AttachmentUploadSessionOut` | 145-172 |  |
| 函数 `initiate_conversation_attachment_upload_session(conversation_id, request_model, request, response, idempotency_key, context, db) -> AttachmentUploadSessionOut \| JSONResponse` | 180-246 |  |
| 函数 `complete_conversation_attachment_upload_session(conversation_id, upload_session_id, request, response, context, db) -> AttachmentUploadSessionOut \| JSONResponse` | 254-308 |  |
| 函数 `upload_conversation_attachment(conversation_id, request, response, file, idempotency_key, context, db) -> InputArtifactUploadOut \| JSONResponse` | 315-399 |  |

## `backend/app/modules/input_artifacts/attachment_context.py`（231 行）

模块说明：Build a bounded, task-scoped attachment context for the Planner.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AttachmentContextError`(RuntimeError) | 25-26 | A frozen attachment cannot safely become model context. |
| 类 `AttachmentContextLimits`() | 30-44 |  |
| 函数 `AttachmentContextLimits.__post_init__() -> None` | 35-44 |  |
| 类 `TaskAttachmentContext`() | 51-60 | Prompt content plus durable-safe selection metadata. |
| 函数 `build_task_attachment_context(db, *, task_id, company_id, storage, limits) -> TaskAttachmentContext` | 63-180 | Load exactly the versions frozen for one task and verify their outputs. |
| 函数 `_read_verified_manifest(*, storage, parse_result, destination_path) -> dict[str, Any]` | 183-204 |  |
| 函数 `_read_verified_extracted_text(*, storage, parse_result, destination_path) -> str` | 207-231 |  |

## `backend/app/modules/input_artifacts/models.py`（763 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `InputArtifact`(Base) | 19-41 |  |
| 类 `InputArtifactVersion`(Base) | 44-114 |  |
| 类 `ArtifactProcessingAttempt`(Base) | 117-181 |  |
| 类 `ArtifactParseResult`(Base) | 184-263 | Immutable, storage-backed output of one successful parse attempt. |
| 类 `ArtifactProcessingJob`(Base) | 266-359 | Durable queue record for one processing stage of one artifact version. |
| 类 `ArtifactProcessingOutboxEvent`(Base) | 362-472 | Durable publication request for one artifact-processing job. |
| 类 `InputArtifactUploadRequest`(Base) | 475-583 |  |
| 类 `InputArtifactUploadSession`(Base) | 586-763 | Server-owned control record for a direct-to-quarantine upload. |

## `backend/app/modules/input_artifacts/outbox_tasks.py`（66 行）

模块说明：Periodic publisher for durable input-artifact processing events.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `publish_pending_artifact_processing_events() -> int` | 22-66 |  |

## `backend/app/modules/input_artifacts/processing/image_ocr.py`（89 行）

模块说明：Local, bounded Tesseract OCR adapter for already-inspected images.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ImageOcrResult`() | 11-13 |  |
| 类 `ImageOcrError`(RuntimeError) | 16-19 |  |
| 函数 `ImageOcrError.__init__(error_code) -> None` | 17-19 |  |
| 类 `TesseractImageOcr`() | 22-69 | Use Tesseract TSV output so confidence is retained with extracted text. |
| 函数 `TesseractImageOcr.__init__(*, languages, timeout_seconds, command_runner) -> None` | 25-36 |  |
| 函数 `TesseractImageOcr.extract(image_path) -> ImageOcrResult` | 38-69 |  |
| 函数 `_parse_tesseract_tsv(tsv) -> ImageOcrResult` | 72-89 |  |

## `backend/app/modules/input_artifacts/processing/parse_worker.py`（133 行）

模块说明：One claimed parse-job execution, independent of the Celery transport.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `execute_parse_job(db, *, job_id, dispatch_generation, processor_name, processor_version, storage_factory, image_limits, pdf_limits, image_ocr, pdf_page_renderer) -> bool` | 32-123 | Claim, parse, persist immutable output, and complete one parse job. |
| 函数 `_fail(db, claim, error_code) -> bool` | 126-133 |  |

## `backend/app/modules/input_artifacts/processing/parser.py`（661 行）

模块说明：Deterministic local parsers for already-scanned input artifacts.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `XlsxParseLimits`() | 18-26 | Budgets enforced before and while reading an XLSX archive. |
| 类 `PdfParseLimits`() | 33-39 | Budgets and quality threshold for PDF text-layer extraction and OCR. |
| 类 `ImageParseLimits`() | 46-49 |  |
| 类 `InputArtifactParseError`(RuntimeError) | 55-60 | A terminal parsing error with a stable user-safe reason code. |
| 函数 `InputArtifactParseError.__init__(error_code) -> None` | 58-60 |  |
| 类 `ParsedInputArtifact`() | 64-70 | A parser result before the Worker persists it to object storage. |
| 函数 `parse_input_artifact_file(*, source_path, original_filename, output_directory, xlsx_limits, pdf_limits, pdf_page_renderer, image_limits, image_ocr) -> ParsedInputArtifact` | 73-152 | Parse one supported local file without evaluating formulas or code. |
| 函数 `_copy_utf8_text(source_path, destination_path) -> int` | 155-168 |  |
| 函数 `_inspect_csv(source_path) -> tuple[list[str], int, int, int]` | 171-192 |  |
| 函数 `_parse_xlsx(*, source_path, output_path, limits) -> ParsedInputArtifact` | 195-279 | Extract an XLSX workbook without evaluating formulas or external links. |
| 函数 `_validate_xlsx_limits(limits) -> None` | 282-294 |  |
| 函数 `_inspect_xlsx_archive(source_path, limits) -> None` | 297-317 |  |
| 函数 `_xlsx_cell_text(value) -> str` | 320-321 |  |
| 类 `_CharacterBudget`() | 325-332 |  |
| 函数 `_CharacterBudget.add(value) -> None` | 329-332 |  |
| 类 `_CountingTextWriter`() | 335-342 |  |
| 函数 `_CountingTextWriter.__init__(target, counter) -> None` | 336-338 |  |
| 函数 `_CountingTextWriter.write(value) -> int` | 340-342 |  |
| 函数 `_parse_pdf(*, source_path, output_path, limits, page_renderer, image_ocr) -> ParsedInputArtifact` | 345-507 | Extract text layers and OCR only pages without one, under bounded budgets. |
| 函数 `_validate_pdf_limits(limits) -> None` | 510-525 |  |
| 函数 `_parse_image(*, source_path, output_path, declared_suffix, limits, image_ocr) -> ParsedInputArtifact` | 528-612 |  |
| 函数 `_extract_ocr_text(image_path, image_ocr) -> tuple[str, float \| None]` | 615-640 |  |
| 函数 `_save_ocr_png(image, destination_path, image_module) -> None` | 643-650 |  |
| 函数 `_validate_image_limits(limits) -> None` | 653-661 |  |

## `backend/app/modules/input_artifacts/processing/pdf_render.py`（70 行）

模块说明：Bounded Poppler adapter for rendering one PDF page for OCR.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `PdfPageRenderError`(RuntimeError) | 8-11 |  |
| 函数 `PdfPageRenderError.__init__(error_code) -> None` | 9-11 |  |
| 类 `PopplerPdfPageRenderer`() | 14-70 |  |
| 函数 `PopplerPdfPageRenderer.__init__(*, timeout_seconds, max_side_pixels, command_runner) -> None` | 15-26 |  |
| 函数 `PopplerPdfPageRenderer.render_page(source_path, page_number, destination_path) -> Path` | 28-70 |  |

## `backend/app/modules/input_artifacts/processing/processing_jobs.py`（978 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClaimedProcessingJob`() | 20-26 |  |
| 类 `ExpiredScanJobRecovery`() | 30-32 |  |
| 类 `ScanJobFailureOutcome`() | 36-38 |  |
| 函数 `claim_scan_job_for_processing(db, *, job_id, expected_dispatch_generation, processor_name, processor_version, lease_seconds) -> ClaimedProcessingJob \| None` | 41-60 |  |
| 函数 `claim_parse_job_for_processing(db, *, job_id, expected_dispatch_generation, processor_name, processor_version, lease_seconds) -> ClaimedProcessingJob \| None` | 63-82 |  |
| 函数 `_claim_processing_job(db, *, job_id, expected_dispatch_generation, processor_name, processor_version, stage, eligible_version_statuses, version_status, lease_seconds) -> ClaimedProcessingJob \| None` | 85-204 |  |
| 函数 `_scan_retry_delay_seconds(retry_count) -> int` | 207-212 |  |
| 函数 `recover_expired_scan_job(db, *, job_id) -> ExpiredScanJobRecovery \| None` | 215-315 |  |
| 函数 `complete_scan_job_processing(db, *, job_id, execution_id, expected_generation) -> bool` | 318-444 |  |
| 函数 `complete_parse_job_processing(db, *, job_id, execution_id, expected_generation, result_schema_version, manifest_object_key, manifest_sha256, extracted_text_object_key, extracted_text_sha256, extracted_text_char_count) -> bool` | 447-616 | Persist the current parse worker's immutable output and mark its version ready. |
| 函数 `fail_parse_job_processing(db, *, job_id, execution_id, expected_generation, error_code) -> bool` | 619-731 | Record a non-retryable parse failure owned by the current worker. |
| 函数 `reject_scan_job_processing(db, *, job_id, execution_id, expected_generation, reason_code) -> bool` | 734-846 | Record a final security-policy rejection owned by the current scanner. |
| 函数 `fail_scan_job_processing(db, *, job_id, execution_id, expected_generation, error_code, retryable) -> ScanJobFailureOutcome \| None` | 849-978 | Record the current scanner failure and schedule its bounded retry if allowed. |

## `backend/app/modules/input_artifacts/processing/processing_outbox.py`（270 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClaimedArtifactProcessingPublication`() | 15-22 |  |
| 函数 `claim_artifact_processing_event_for_publication(db, *, event_id, lease_seconds) -> ClaimedArtifactProcessingPublication \| None` | 25-98 |  |
| 函数 `mark_artifact_processing_event_published(db, *, claim, broker_message_id) -> bool` | 101-154 |  |
| 函数 `return_artifact_processing_event_to_pending(db, *, claim, failure_code) -> bool` | 157-211 |  |
| 函数 `pending_artifact_processing_event_ids(db, *, limit) -> list[int]` | 214-228 |  |
| 函数 `publish_artifact_processing_event(db, *, event_id, enqueue, lease_seconds) -> bool` | 231-270 |  |

## `backend/app/modules/input_artifacts/processing/processing_storage.py`（254 行）

模块说明：Controlled object-storage access used only by artifact-processing Workers.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ArtifactProcessingStorageUnavailableError`(RuntimeError) | 15-16 | The configured object storage cannot serve the processing Worker. |
| 类 `ArtifactProcessingObjectNotFoundError`(RuntimeError) | 19-20 | A quarantined object expected by a persisted Version is unavailable. |
| 类 `StoredProcessingObject`() | 24-27 |  |
| 类 `ArtifactProcessingStorage`(Protocol) | 30-61 |  |
| 函数 `ArtifactProcessingStorage.download_quarantine_object(*, object_key, destination_path) -> StoredProcessingObject` | 33-38 |  |
| 函数 `ArtifactProcessingStorage.download_parsed_object(*, object_key, destination_path) -> StoredProcessingObject` | 40-45 |  |
| 函数 `ArtifactProcessingStorage.write_parsed_object(*, object_key, content, content_type) -> StoredProcessingObject` | 47-53 |  |
| 函数 `ArtifactProcessingStorage.write_parsed_file(*, object_key, source_path, content_type) -> StoredProcessingObject` | 55-61 |  |
| 类 `S3ArtifactProcessingStorage`() | 64-213 |  |
| 函数 `S3ArtifactProcessingStorage.__init__(*, settings) -> None` | 67-72 |  |
| 函数 `S3ArtifactProcessingStorage.download_quarantine_object(*, object_key, destination_path) -> StoredProcessingObject` | 74-86 |  |
| 函数 `S3ArtifactProcessingStorage.download_parsed_object(*, object_key, destination_path) -> StoredProcessingObject` | 88-101 | Download a parser output for a task-scoped, integrity-checked read. |
| 函数 `S3ArtifactProcessingStorage._download_object(*, object_key, destination_path, prefix, not_found_message, unavailable_message) -> StoredProcessingObject` | 103-130 |  |
| 函数 `S3ArtifactProcessingStorage.write_parsed_object(*, object_key, content, content_type) -> StoredProcessingObject` | 132-160 |  |
| 函数 `S3ArtifactProcessingStorage.write_parsed_file(*, object_key, source_path, content_type) -> StoredProcessingObject` | 162-192 |  |
| 函数 `S3ArtifactProcessingStorage._client()` | 194-213 |  |
| 函数 `get_artifact_processing_storage(settings) -> ArtifactProcessingStorage` | 216-217 |  |
| 函数 `_require_object_key(object_key, *, prefix) -> None` | 220-224 |  |
| 函数 `_file_size_and_sha256(path) -> tuple[int, str]` | 227-234 |  |
| 函数 `_is_not_found_error(exc) -> bool` | 237-239 |  |
| 函数 `_has_complete_s3_configuration(settings) -> bool` | 242-254 |  |

## `backend/app/modules/input_artifacts/processing/scan_worker.py`（120 行）

模块说明：One claimed scan-job execution, independent of the Celery transport.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `execute_scan_job(db, *, job_id, dispatch_generation, processor_name, processor_version, scanner_factory, storage_factory) -> bool` | 23-92 | Claim, download, verify, scan, and persist exactly one scan outcome. |
| 函数 `_fail_retryable(db, claim, error_code) -> bool` | 95-106 |  |
| 函数 `_fail_non_retryable(db, claim, error_code) -> bool` | 109-120 |  |

## `backend/app/modules/input_artifacts/processing/scanner.py`（92 行）

模块说明：ClamAV daemon adapter. It returns a scan fact and never mutates database state.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClamDProtocolError`(RuntimeError) | 14-15 | clamd returned a reply that cannot be trusted as a scan result. |
| 类 `ScanResult`() | 19-21 |  |
| 类 `ClamDScanner`() | 24-74 | Stream one local file to a private clamd TCP endpoint. |
| 函数 `ClamDScanner.__init__(*, host, port, timeout_seconds) -> None` | 29-45 |  |
| 函数 `ClamDScanner.scan_file(path) -> ScanResult` | 47-74 |  |
| 函数 `_read_clamd_reply(connection) -> str` | 77-92 |  |

## `backend/app/modules/input_artifacts/repository.py`（262 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `add_input_artifact(db, *, company_id, uploaded_by_user_id, kind) -> InputArtifact` | 14-28 |  |
| 函数 `add_input_artifact_version(db, *, artifact_id, original_filename, declared_extension, raw_object_key, byte_size, sha256, declared_mime_type) -> InputArtifactVersion` | 31-55 |  |
| 函数 `get_input_artifact_version_for_company(db, *, version_id, company_id) -> InputArtifactVersion \| None` | 58-72 |  |
| 函数 `get_ready_owned_input_artifact_versions(db, *, version_ids, company_id, uploaded_by_user_id) -> list[InputArtifactVersion]` | 75-94 |  |
| 函数 `get_input_artifact_upload_request(db, *, company_id, submitted_by_user_id, conversation_id, idempotency_key) -> InputArtifactUploadRequest \| None` | 97-114 |  |
| 函数 `add_receiving_input_artifact_upload_request(db, *, company_id, submitted_by_user_id, conversation_id, idempotency_key, trace_request_id, lease_expires_at, request_fingerprint) -> InputArtifactUploadRequest` | 117-140 |  |
| 函数 `add_input_artifact_upload_session(db, *, public_id, company_id, submitted_by_user_id, conversation_id, idempotency_key, request_fingerprint, client_filename, client_reported_byte_size, client_reported_mime_type, client_reported_sha256, upload_policy_version, storage_provider, staging_object_key, upload_expires_at, trace_request_id) -> InputArtifactUploadSession` | 143-181 |  |
| 函数 `add_artifact_processing_job(db, *, company_id, artifact_version_id, stage, max_attempts, trace_request_id) -> ArtifactProcessingJob` | 184-202 |  |
| 函数 `add_artifact_processing_outbox_event(db, *, company_id, job_id, dispatch_generation, trace_request_id) -> ArtifactProcessingOutboxEvent` | 205-222 |  |
| 函数 `get_input_artifact_upload_session(db, *, company_id, submitted_by_user_id, conversation_id, idempotency_key) -> InputArtifactUploadSession \| None` | 225-242 |  |
| 函数 `get_input_artifact_upload_session_by_public_id(db, *, public_id, company_id, submitted_by_user_id, conversation_id, for_update) -> InputArtifactUploadSession \| None` | 245-262 |  |

## `backend/app/modules/input_artifacts/schemas.py`（67 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `InputArtifactVersionReceiptOut`(BaseModel) | 23-25 |  |
| 类 `InputArtifactUploadOut`(BaseModel) | 28-33 |  |
| 类 `AttachmentUploadSessionInitiate`(BaseModel) | 46-52 | Fields are populated by the client from the selected File object. |
| 类 `DirectUploadFormOut`(BaseModel) | 55-59 |  |
| 类 `AttachmentUploadSessionOut`(BaseModel) | 62-67 |  |

## `backend/app/modules/input_artifacts/storage.py`（224 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `StoredInputArtifactFile`() | 30-36 |  |
| 类 `InspectedInputArtifactFile`() | 40-44 |  |
| 类 `DeclaredInputArtifactUpload`() | 48-55 | Untrusted browser metadata accepted before direct object upload. |
| 函数 `discard_stored_input_artifact_file(stored_file, *, settings) -> None` | 58-71 | Remove a newly stored quarantine file during a failed ingest transaction. |
| 函数 `normalize_input_artifact_filename(original_filename) -> tuple[str, str, _ArtifactCategory]` | 74-90 |  |
| 函数 `inspect_input_artifact_file(*, file_stream, original_filename, settings) -> InspectedInputArtifactFile` | 93-125 |  |
| 函数 `_max_size_bytes(settings, category) -> int` | 128-134 |  |
| 函数 `validate_declared_input_artifact_upload(*, original_filename, byte_size, declared_mime_type, client_reported_sha256, settings) -> DeclaredInputArtifactUpload` | 137-175 | Validate metadata without reading file bytes in the API process. |
| 函数 `store_input_artifact_file(*, file_stream, original_filename, settings) -> StoredInputArtifactFile` | 178-224 | Store an untrusted file in quarantine and return verified raw metadata. |

## `backend/app/modules/input_artifacts/tasks.py`（80 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `process_scan_job(company_id, job_id, dispatch_generation) -> bool` | 19-42 |  |
| 函数 `process_parse_job(company_id, job_id, dispatch_generation) -> bool` | 46-80 |  |

## `backend/app/modules/input_artifacts/upload/direct_ingestion.py`（48 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `ingest_received_input_artifact(db, *, company_id, uploaded_by_user_id, kind, file_stream, original_filename, settings, declared_mime_type) -> InputArtifactVersion` | 13-48 | Store one untrusted file, then atomically create its received database version. |

## `backend/app/modules/input_artifacts/upload/direct_upload_storage.py`（213 行）

模块说明：S3-compatible direct upload contract for quarantined input artifacts.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DirectUploadStorageUnavailableError`(RuntimeError) | 11-12 | No correctly configured provider can issue a direct upload policy. |
| 类 `DirectUploadObjectNotFoundError`(RuntimeError) | 15-16 | The browser reported completion before its quarantined object exists. |
| 类 `DirectUploadObjectIntegrityError`(RuntimeError) | 19-20 | The provider cannot return the integrity metadata required for acceptance. |
| 类 `DirectUploadForm`() | 24-27 |  |
| 类 `StoredQuarantineObject`() | 31-33 |  |
| 类 `DirectUploadStorage`(Protocol) | 36-52 |  |
| 函数 `DirectUploadStorage.create_quarantine_upload_form(*, object_key, byte_size, sha256_hex, expires_at) -> DirectUploadForm` | 39-46 |  |
| 函数 `DirectUploadStorage.inspect_quarantine_object(*, object_key) -> StoredQuarantineObject` | 48-52 |  |
| 类 `S3DirectUploadStorage`() | 55-190 |  |
| 函数 `S3DirectUploadStorage.__init__(*, settings) -> None` | 58-63 |  |
| 函数 `S3DirectUploadStorage.create_quarantine_upload_form(*, object_key, byte_size, sha256_hex, expires_at) -> DirectUploadForm` | 65-125 |  |
| 函数 `S3DirectUploadStorage.inspect_quarantine_object(*, object_key) -> StoredQuarantineObject` | 127-190 |  |
| 函数 `get_direct_upload_storage(settings) -> DirectUploadStorage` | 193-194 |  |
| 函数 `_has_complete_s3_configuration(settings) -> bool` | 197-213 |  |

## `backend/app/modules/input_artifacts/upload/request_fingerprint.py`（79 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_validate_positive_identifier(value, *, field_name) -> int` | 12-15 |  |
| 函数 `_validate_input_artifact_kind(kind) -> str` | 18-21 |  |
| 函数 `_validate_content_sha256(content_sha256) -> str` | 24-36 |  |
| 函数 `build_input_artifact_request_fingerprint(*, company_id, submitted_by_user_id, conversation_id, kind, original_filename, content_sha256) -> str` | 39-79 |  |

## `backend/app/modules/input_artifacts/upload/upload_requests.py`（384 行）

模块说明：Reservation of an upload request before its untrusted bytes are stored.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `UploadRequestReservation`() | 20-22 |  |
| 类 `UploadRequestFencedError`(RuntimeError) | 25-26 | The request no longer owns the valid upload lease. |
| 类 `UploadRequestFingerprintConflictError`(ValueError) | 29-30 | The idempotency key was reused with different request content. |
| 函数 `reserve_input_artifact_upload_request(db, *, context, conversation_id, idempotency_key, trace_request_id, lease_duration, request_fingerprint) -> UploadRequestReservation \| None` | 33-184 | Reserve one attachment upload without allowing a stale request to win. |
| 函数 `complete_input_artifact_upload_request(db, *, context, conversation_id, idempotency_key, attempt_generation, payload_hash, artifact_version_id) -> InputArtifactUploadRequest \| None` | 187-297 | Publish a stored version only while this request still owns its lease. |
| 函数 `finish_upload_request_with_error(db, *, context, conversation_id, idempotency_key, attempt_generation, status, error_code) -> InputArtifactUploadRequest \| None` | 300-384 |  |

## `backend/app/modules/input_artifacts/upload/upload_service.py`（241 行）

模块说明：The complete synchronous receipt of one conversation attachment.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `InputArtifactContentMismatchError`(ValueError) | 40-41 | The stored bytes differ from the bytes inspected before reservation. |
| 类 `UploadAttachmentCommand`() | 45-54 | All request-specific input for one attachment receipt. |
| 类 `UploadAttachmentOutcome`() | 58-62 | The only upload result exposed to the HTTP layer. |
| 函数 `process_conversation_attachment_upload(db, *, command, settings) -> UploadAttachmentOutcome \| None` | 65-116 | Receive one attachment without exposing intermediate state to the route. |
| 函数 `_store_reserved_attachment(db, *, command, reservation, inspected_file, settings) -> UploadAttachmentOutcome` | 119-210 |  |
| 函数 `_discard_if_stored(stored_file, *, settings) -> None` | 213-219 |  |
| 函数 `_failed_outcome(db, *, command, request, status, error_code) -> UploadAttachmentOutcome` | 222-241 |  |

## `backend/app/modules/input_artifacts/upload/upload_session_fingerprint.py`（31 行）

模块说明：Canonical idempotency fingerprint for direct-upload initiation.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `build_direct_upload_session_fingerprint(*, company_id, submitted_by_user_id, conversation_id, declared_upload, upload_policy_version) -> str` | 9-31 |  |

## `backend/app/modules/input_artifacts/upload/upload_sessions.py`（576 行）

模块说明：Initiate direct, browser-to-object-storage attachment uploads.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `UploadSessionFingerprintConflictError`(ValueError) | 42-43 | An idempotency key was reused for a different direct upload intent. |
| 类 `InitiateAttachmentUploadCommand`() | 47-55 |  |
| 类 `UploadSessionInitiationOutcome`() | 59-62 |  |
| 类 `CompleteAttachmentUploadCommand`() | 66-70 |  |
| 类 `UploadSessionCompletionOutcome`() | 74-77 |  |
| 函数 `initiate_conversation_attachment_upload(db, *, command, settings, direct_upload_storage) -> UploadSessionInitiationOutcome \| None` | 80-119 | Create or replay a session; never receive raw bytes in this process. |
| 函数 `_reserve_or_replay_upload_session(db, *, command, declared_upload, fingerprint, settings, direct_upload_storage) -> UploadSessionInitiationOutcome` | 122-207 |  |
| 函数 `_replay_existing_session(db, *, session, fingerprint, now, settings, direct_upload_storage) -> UploadSessionInitiationOutcome` | 210-236 |  |
| 函数 `_expire_session(db, *, session, now) -> None` | 239-265 |  |
| 函数 `complete_conversation_attachment_upload(db, *, command, direct_upload_storage) -> UploadSessionCompletionOutcome \| None` | 268-330 | Accept a direct upload only after object-storage metadata verification. |
| 类 `_FinalizationClaim`() | 334-338 |  |
| 函数 `_claim_upload_session_finalization(db, *, command) -> _FinalizationClaim` | 341-394 |  |
| 函数 `_completion_outcome_for_existing_session(db, *, session, disposition, company_id) -> UploadSessionCompletionOutcome \| None` | 397-421 |  |
| 函数 `_fail_claimed_upload_session(db, *, command, claim, failure_code) -> UploadSessionCompletionOutcome` | 424-439 |  |
| 函数 `_complete_claimed_upload_session(db, *, command, claim, verified_byte_size, verified_sha256) -> UploadSessionCompletionOutcome` | 442-491 |  |
| 函数 `_lock_claimed_session(db, *, command, claim) -> InputArtifactUploadSession` | 494-516 |  |
| 函数 `_normalize_command(command) -> InitiateAttachmentUploadCommand` | 519-548 |  |
| 函数 `_normalize_completion_command(command) -> CompleteAttachmentUploadCommand` | 551-576 |  |

## `backend/app/modules/input_artifacts/versions.py`（107 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_require_positive_id(value, field_name) -> None` | 15-17 |  |
| 函数 `_normalize_filename(original_filename) -> tuple[str, str \| None]` | 20-33 |  |
| 函数 `_normalize_optional_mime_type(value) -> str \| None` | 36-44 |  |
| 函数 `create_received_input_artifact_version(db, *, company_id, uploaded_by_user_id, kind, original_filename, raw_object_key, byte_size, sha256, declared_mime_type, commit) -> InputArtifactVersion` | 47-107 | Persist one received version. |

## `backend/app/modules/knowledge/agent.py`（318 行）

模块说明：Knowledge Agent —— 基于文档知识回答问题的 Agent

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `answer_context_manifest(question, system_prompt, evidences, confirmed_facts) -> ContextManifest \| None` | 42-69 | The manifest recorded with one Knowledge answer; enforce refuses one that |
| 类 `KnowledgeAgent`(Agent) | 72-318 | 只使用文档知识工具的 Agent |
| 函数 `KnowledgeAgent.__init__(rag_tool, gateway, support_check) -> None` | 75-83 |  |
| 函数 `KnowledgeAgent.name() -> str` | 86-87 |  |
| 函数 `KnowledgeAgent.description() -> str` | 90-91 |  |
| 函数 `KnowledgeAgent.allowed_tools() -> list[Tool]` | 94-95 |  |
| 函数 `KnowledgeAgent._retrieval_brief(input) -> tuple[RetrievalBrief, list]` | 98-115 |  |
| 函数 `KnowledgeAgent._search_parameters(input) -> dict` | 118-131 |  |
| 函数 `KnowledgeAgent.run(input) -> AgentOutput` | 133-238 | 执行知识检索 |
| 函数 `KnowledgeAgent._cited_output(*, input, gateway, answer, cited_chunk_ids, evidences, validity_window, brief, attempts) -> AgentOutput` | 240-318 | Run the support check and keep only what the citations really say. |

## `backend/app/modules/knowledge/analysis_result.py`（11 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisCitation`(BaseModel) | 4-5 |  |
| 类 `AnalysisResult`(BaseModel) | 8-11 |  |

## `backend/app/modules/knowledge/mcp_adapter.py`（340 行）

模块说明：A local MCP transport adapter for the existing read-only evidence tool.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `document_scope_sha256(company_id, document_ids) -> str` | 56-63 | Create a stable scope binding without sending a second document list. |
| 函数 `runtime_context_sha256(context) -> str` | 66-69 | Bind the MCP response to the Runtime-injected authorization context. |
| 函数 `_is_valid_runtime_context(context, *, company_id, document_ids) -> TypeGuard[dict[str, Any]]` | 72-94 |  |
| 函数 `_is_compatible_catalog(catalog) -> bool` | 97-111 | Require the one fixed capability and its bounded input contract. |
| 函数 `_has_locked_mcp_sdk() -> bool` | 114-118 |  |
| 函数 `_stdio_runtime_environment() -> dict[str, str]` | 121-146 | Pass only the configuration required by the read-only RAG subprocess. |
| 函数 `create_evidence_mcp_server(reader) -> MCPServer` | 149-199 | Expose one read-only tool; authorization remains with ToolRuntime. |
| 类 `McpEvidenceReadTool`(Tool) | 202-331 | Keep the local Tool contract while using a constrained MCP catalog. |
| 函数 `McpEvidenceReadTool.__init__(server) -> None` | 205-206 |  |
| 函数 `McpEvidenceReadTool.stdio() -> 'McpEvidenceReadTool'` | 209-216 |  |
| 函数 `McpEvidenceReadTool.name() -> str` | 219-220 |  |
| 函数 `McpEvidenceReadTool.description() -> str` | 223-224 |  |
| 函数 `McpEvidenceReadTool.execute(input) -> ToolOutput` | 226-235 |  |
| 异步函数 `McpEvidenceReadTool._execute(parameters) -> ToolOutput` | 237-331 |  |
| 函数 `main() -> None` | 334-336 |  |

## `backend/app/modules/knowledge/rag/embeddings.py`（10 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `EmbeddingProvider`(ABC) | 4-10 | Embedding 提供者抽象类 |
| 函数 `EmbeddingProvider.embed(text) -> list[float]` | 8-10 | 将文本转换为向量 |

## `backend/app/modules/knowledge/rag/embeddings_local.py`（45 行）

模块说明：本地 Embedding 实现（基于 sentence-transformers）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_get_model()` | 18-32 | 懒加载模型，只加载一次 |
| 类 `LocalEmbeddingProvider`(EmbeddingProvider) | 35-45 | 使用 sentence-transformers 本地模型生成向量 |
| 函数 `LocalEmbeddingProvider.__init__()` | 38-39 |  |
| 函数 `LocalEmbeddingProvider.embed(text) -> list[float]` | 41-42 |  |
| 函数 `LocalEmbeddingProvider.embed_batch(texts) -> list[list[float]]` | 44-45 |  |

## `backend/app/modules/knowledge/rag/engine.py`（153 行）

模块说明：可靠RAG引擎

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `EvidenceRef`() | 13-30 | 一条证据引用 |
| 类 `RAGResult`() | 34-40 | RAG 处理结果 |
| 函数 `_validity_attributes(evidence) -> str` | 43-51 | Registered validity for the model; absent when nothing was registered. |
| 函数 `fit_evidences(question, evidences, max_chars) -> list[EvidenceRef]` | 59-94 | The evidences the answer reads, best first, within ``max_chars``. |
| 函数 `build_prompt(question, evidences, max_chars) -> tuple[str, str, set[int]]` | 97-122 | 返回 (system_prompt, user_prompt, allowed_chunk_ids)。 |
| 函数 `keep_relevant(evidences, min_score) -> list[EvidenceRef]` | 125-131 | Drop chunks the reranker considers irrelevant. |
| 函数 `check_sufficiency(evidences, question, min_evidences, min_avg_score) -> bool` | 134-153 | 判断证据是否充分 |

## `backend/app/modules/knowledge/rag/policy.py`（56 行）

模块说明：Server-owned retrieval profiles used for isolated RAG comparisons.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RetrievalPolicy`() | 13-23 |  |
| 函数 `RetrievalPolicy.__post_init__() -> None` | 19-23 |  |

## `backend/app/modules/knowledge/rag/reranker.py`（84 行）

模块说明：将向量召回的候选 chunk 按问题相关性重新排序。

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Reranker`(Protocol) | 13-18 | 相关性重排协议，方便在测试或后续服务化时替换实现。 |
| 函数 `Reranker.score(question, passages) -> list[float]` | 16-18 | 返回与 passages 一一对应、范围为 0 到 1 的相关性分数。 |
| 函数 `_get_model(model_name)` | 24-34 |  |
| 类 `LocalCrossEncoderReranker`() | 37-58 | 使用本地 CrossEncoder 对“问题 + chunk”进行语义相关性评分。 |
| 函数 `LocalCrossEncoderReranker.__init__(model_name) -> None` | 40-41 |  |
| 函数 `LocalCrossEncoderReranker.score(question, passages) -> list[float]` | 43-58 |  |
| 函数 `rerank_evidences(question, evidences, reranker, *, top_k) -> list[EvidenceRef]` | 61-84 | 保留相关性最高的候选，并保留原始向量分数供审计。 |

## `backend/app/modules/knowledge/rag/result_parser.py`（30 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `parse_analysis_result(raw_output, allowed_chunk_ids) -> AnalysisResult` | 8-30 |  |

## `backend/app/modules/knowledge/rag/retrieval.py`（158 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_iso(value) -> str \| None` | 19-20 |  |
| 函数 `retrieve_evidence(db, question, company_id, embedder, *, top_k, min_score, document_ids, chunk_strategies, validity, keyword_tokenizer) -> list[EvidenceRef]` | 23-118 | 为指定公司内已冻结的文档范围检索证据。 |
| 函数 `_evidence(row, labels) -> EvidenceRef` | 121-137 |  |
| 函数 `_fuse_routes(routes) -> list[EvidenceRef]` | 140-158 | Reciprocal rank fusion: rank position decides, so routes with different |

## `backend/app/modules/knowledge/rag/support.py`（242 行）

模块说明：Check each sentence of a document answer against the chunks it relies on.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_system_prompt(has_confirmed_facts) -> str` | 29-39 |  |
| 类 `SentenceVerdict`(BaseModel) | 42-48 |  |
| 类 `SupportVerdicts`(BaseModel) | 51-53 |  |
| 类 `CheckedSentence`() | 57-63 |  |
| 类 `SupportOutcome`() | 67-77 |  |
| 函数 `SupportOutcome.answer() -> str` | 71-72 |  |
| 函数 `SupportOutcome.cited_chunk_ids() -> list[int]` | 75-77 |  |
| 函数 `split_sentences(answer) -> list[str]` | 80-82 | Split on Chinese sentence ends; a decimal point never ends a sentence. |
| 函数 `_valid_in_window(evidence, window) -> bool` | 85-89 |  |
| 函数 `_render_material(evidences) -> str` | 92-110 | The chunks exactly as the model reads them: id, validity, scope, words. |
| 函数 `_render_prompt(question, sentences, evidences, confirmed_facts) -> str` | 113-128 |  |
| 函数 `_parse(raw_output) -> dict[int, SentenceVerdict]` | 131-136 |  |
| 函数 `apply_code_checks(sentences, verdicts, evidences, window, *, has_confirmed_facts) -> SupportOutcome` | 139-180 |  |
| 函数 `support_context_manifest(question, sentences, evidences, confirmed_facts, system_prompt) -> ContextManifest \| None` | 183-211 | The manifest recorded with one support check; enforce refuses one that |
| 函数 `check_support(gateway, *, question, answer, evidences, window, confirmed_facts) -> SupportOutcome` | 214-242 |  |

## `backend/app/modules/knowledge/rag/validity.py`（121 行）

模块说明：Work out from the question which period a document must be valid in.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ValidityWindow`() | 39-53 |  |
| 函数 `ValidityWindow.to_parameter() -> list[str]` | 43-44 |  |
| 函数 `ValidityWindow.from_parameter(value) -> 'ValidityWindow'` | 47-53 |  |
| 函数 `business_today() -> date` | 56-58 | Today on the company's calendar; validity dates are written in this zone. |
| 函数 `_number(token) -> int` | 61-62 |  |
| 函数 `_months(year, first, last) -> tuple[date, date]` | 65-69 |  |
| 函数 `explicit_periods(question, today) -> list[tuple[date, date]]` | 72-107 |  |
| 函数 `resolve_validity_window(question, today) -> ValidityWindow` | 110-121 | The period to keep documents for, widened rather than guessed when unclear. |

## `backend/app/modules/knowledge/schemas.py`（19 行）

模块说明：The bounded, fact-led input Knowledge may use for document retrieval.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RetrievalBrief`(BaseModel) | 6-19 |  |
| 函数 `RetrievalBrief.render_query() -> str` | 11-19 |  |

## `backend/app/modules/knowledge/tool.py`（286 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RAGTool`(Tool) | 41-286 |  |
| 函数 `RAGTool.__init__(reranker, retrieval_policy, degrade_on_rerank_failure) -> None` | 42-53 |  |
| 函数 `RAGTool.name() -> str` | 56-57 |  |
| 函数 `RAGTool.description() -> str` | 60-61 |  |
| 函数 `RAGTool.execute(input) -> ToolOutput` | 63-286 |  |

## `backend/app/modules/knowledge/tool_agent.py`（285 行）

模块说明：Knowledge Agent whose model may search again before it answers.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SearchDocumentsArgs`(BaseModel) | 38-40 |  |
| 类 `SubmitAnswerArgs`(BaseModel) | 43-48 |  |
| 类 `ReportNoEvidenceArgs`(BaseModel) | 51-53 |  |
| 函数 `_shown(evidence) -> dict` | 92-102 | Only what answering needs: scores and internal fields stay on the server. |
| 类 `_KnowledgeToolSession`() | 105-204 |  |
| 函数 `_KnowledgeToolSession.__init__(agent, input, gateway) -> None` | 106-121 |  |
| 函数 `_KnowledgeToolSession.handlers() -> dict` | 124-129 |  |
| 函数 `_KnowledgeToolSession.search(query) -> ToolOutput` | 131-145 |  |
| 函数 `_KnowledgeToolSession.render(result) -> dict` | 147-151 |  |
| 函数 `_KnowledgeToolSession.search_documents(args) -> ToolReply` | 153-173 |  |
| 函数 `_KnowledgeToolSession.submit_answer(args) -> ToolReply` | 175-194 |  |
| 函数 `_KnowledgeToolSession.report_no_evidence(_args) -> ToolReply` | 196-204 |  |
| 类 `ToolCallingKnowledgeAgent`(KnowledgeAgent) | 207-285 | Same output contract as KnowledgeAgent, so the workflow cannot tell. |
| 函数 `ToolCallingKnowledgeAgent.__init__(*args, limits, **kwargs) -> None` | 210-216 |  |
| 函数 `ToolCallingKnowledgeAgent._user_prompt(input, session, first) -> str` | 218-233 |  |
| 函数 `ToolCallingKnowledgeAgent.run(input) -> AgentOutput` | 235-285 |  |

## `backend/app/modules/memory/api.py`（163 行）

模块说明：Review memories: people decide what happens to a memory, never its content.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MemoryOut`(BaseModel) | 26-41 |  |
| 类 `MemoryAuditOut`(BaseModel) | 44-53 |  |
| 类 `FlagRequest`(BaseModel) | 56-57 |  |
| 类 `ReviewRequest`(BaseModel) | 60-63 |  |
| 函数 `_is_admin(context) -> bool` | 66-67 |  |
| 函数 `_visible_memory(db, memory_id, context) -> AnalysisMemory` | 70-81 | Another company's memory and a colleague's memory both look like not found. |
| 函数 `list_memories(status, limit, context, db)` | 85-98 |  |
| 函数 `list_memory_audit(memory_id, context, db)` | 102-116 |  |
| 函数 `flag(memory_id, request, context, db)` | 120-138 |  |
| 函数 `review(memory_id, request, context, db)` | 142-163 |  |

## `backend/app/modules/memory/models.py`（126 行）

模块说明：Planner-only durable memory derived from already validated reports.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisMemory`(Base) | 25-93 |  |
| 类 `MemoryAuditEvent`(Base) | 96-126 |  |

## `backend/app/modules/memory/service.py`（491 行）

模块说明：Bounded planner-memory reads, report-derived writes and the memory lifecycle.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MemoryTransitionError`(ValueError) | 34-35 | The requested change is not allowed from the memory's current status. |
| 函数 `_planner_memory_payload(row) -> dict` | 38-44 |  |
| 函数 `_memory_tokens(payload) -> int` | 47-49 |  |
| 函数 `_facts_text(row) -> str` | 52-54 |  |
| 函数 `_token_weight(token) -> int` | 57-61 | A customer or supplier number says far more than a common word or a year. |
| 函数 `memory_relevance(question, text) -> float` | 64-70 | Share of the question's weighted words that the memory also contains. |
| 函数 `_recency(created_at, now) -> float` | 73-75 |  |
| 函数 `select_planner_memories(db, *, company_id, user_id, question, limit, max_tokens, record_use) -> tuple[list[dict], dict]` | 78-187 |  |
| 函数 `planner_memories(db, *, company_id, user_id, limit) -> list[dict]` | 190-197 | Compatibility wrapper for callers that only need bounded memory payloads. |
| 函数 `_audit(db, memory, *, action, actor_kind, actor_user_id, reason, details) -> None` | 200-221 |  |
| 函数 `subject_key_for(question) -> str` | 224-227 | The same question asked again is about the same subject. |
| 函数 `persist_report_memory(db, *, task, report) -> AnalysisMemory \| None` | 230-331 | Persist bounded, source-linked facts only after a report is published. |
| 函数 `_same_facts(left, right) -> bool` | 334-340 |  |
| 函数 `flag_memory(db, memory, *, actor_kind, reason, actor_user_id) -> None` | 343-362 | Stop using a memory until a person looks at it; nothing is removed yet. |
| 函数 `flag_memories_from_model(db, *, company_id, flags, allowed_ids) -> list[int]` | 365-388 | Apply a model's suspicions, only to memories this task really used. |
| 类 `MemoryReview`() | 392-396 |  |
| 函数 `review_memory(db, memory, review) -> None` | 399-439 | A person's decision on a flagged memory. |
| 函数 `cleanup_memories(db, *, company_id, now) -> dict[str, int]` | 442-491 | Soft-delete what has outlived retention, then purge what was deleted long ago. |

## `backend/app/modules/memory/sources.py`（34 行）

模块说明：Provenance and idempotency key for durable planner memory.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `MemorySource`(Base) | 14-34 |  |

## `backend/app/modules/memory/tasks.py`（35 行）

模块说明：Daily memory cleanup, one company at a time so one failure stays contained.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `cleanup_expired_memories() -> dict[str, int]` | 15-35 |  |

## `backend/app/modules/observability/api.py`（18 行）

模块说明：Company-admin operational telemetry API.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_task_metrics_endpoint(context, db) -> TaskMetricsOut` | 14-18 |  |

## `backend/app/modules/observability/health_api.py`（33 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_health()` | 13-14 |  |
| 函数 `get_liveness()` | 18-19 |  |
| 函数 `get_readiness(db)` | 23-33 |  |

## `backend/app/modules/observability/health_schemas.py`（9 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `HealthResponse`(BaseModel) | 4-9 |  |

## `backend/app/modules/observability/health_service.py`（53 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_readiness_service(db) -> dict[str, str]` | 10-53 |  |

## `backend/app/modules/observability/metrics_exporter.py`（208 行）

模块说明：Prometheus exporter for platform state read from the database (O2a).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `read_only_engine() -> Engine` | 66-86 |  |
| 函数 `heartbeat_age_seconds(directory, name, now) -> float \| None` | 89-93 |  |
| 函数 `build_metrics(results, heartbeat_ages, *, up, duration) -> Iterator[GaugeMetricFamily]` | 96-168 | Turn query rows into metric families; statuses with no rows report 0. |
| 类 `PlatformCollector`(Collector) | 171-194 |  |
| 函数 `PlatformCollector.__init__(engine, heartbeat_dir) -> None` | 172-174 |  |
| 函数 `PlatformCollector.collect() -> Iterable[GaugeMetricFamily]` | 176-194 |  |
| 函数 `main() -> None` | 197-204 |  |

## `backend/app/modules/observability/rejection_audit.py`（61 行）

模块说明：Minimal, payload-free audit record for denied analysis submissions.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisRequestRejection`(Base) | 17-34 |  |
| 函数 `record_analysis_request_rejection(*, company_id, request_id, operation, status_code) -> None` | 37-61 | Persist one correlation record without changing an already-denied response. |

## `backend/app/modules/observability/repository.py`（73 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `check_database(db) -> bool` | 12-13 |  |
| 函数 `check_redis() -> bool` | 16-27 |  |
| 函数 `check_object_storage() -> str` | 30-61 |  |
| 函数 `check_task_capacity() -> str` | 64-73 | Report whether new analysis-task admission is currently possible. |

## `backend/app/modules/observability/schemas.py`（22 行）

模块说明：Safe, company-scoped operational metrics for analysis tasks.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `TaskMetricsOut`(BaseModel) | 6-22 |  |

## `backend/app/modules/observability/service.py`（102 行）

模块说明：Aggregate only persisted, non-sensitive task telemetry for one company.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_percentile(values, percentile) -> int \| None` | 13-18 |  |
| 函数 `_nested_status(result_data, key) -> str \| None` | 21-25 |  |
| 函数 `_citation_validation_failed(result_data) -> bool \| None` | 28-35 |  |
| 函数 `get_company_task_metrics(db, *, company_id) -> TaskMetricsOut` | 38-102 |  |

## `backend/app/modules/organizations/access.py`（72 行）

模块说明：Centralized current-company authorization dependencies.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `CurrentCompanyContext`() | 18-25 |  |
| 函数 `CurrentCompanyContext.role() -> str` | 24-25 |  |
| 函数 `get_current_company_context(request, current_user, db) -> CurrentCompanyContext` | 28-47 |  |
| 函数 `require_admin(context) -> CurrentCompanyContext` | 50-55 |  |
| 函数 `require_owner(context) -> CurrentCompanyContext` | 58-63 |  |
| 函数 `require_analysis_permission(context) -> CurrentCompanyContext` | 66-72 | Allow only roles that may query a company data source. |

## `backend/app/modules/organizations/api.py`（510 行）

模块说明：Current-company management API.  Clients never select a company id.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_source_out(source) -> BusinessDataSourceOut` | 55-65 |  |
| 函数 `_member_out(db, member) -> CompanyMemberOut` | 68-81 |  |
| 函数 `_application_out(db, application) -> MembershipApplicationOut` | 84-95 | Expose applicant identity only to an administrator of the same company. |
| 函数 `bootstrap_company(request, current_user, db)` | 101-110 |  |
| 函数 `get_my_company(context)` | 114-124 |  |
| 函数 `get_company_resources(context, db)` | 128-147 |  |
| 函数 `list_data_sources(context, db)` | 151-160 |  |
| 函数 `list_assistant_data_sources(context, db)` | 166-181 |  |
| 函数 `list_data_connections_endpoint(context, db)` | 185-192 |  |
| 函数 `create_data_source_endpoint(request, context, db)` | 200-219 |  |
| 函数 `_current_source_or_404(db, context, data_source_id)` | 222-230 |  |
| 函数 `get_data_source_endpoint(data_source_id, context, db)` | 236-241 |  |
| 函数 `discover_schema_endpoint(data_source_id, context, db)` | 249-263 |  |
| 函数 `list_schema_snapshots(data_source_id, context, db)` | 270-276 |  |
| 函数 `get_active_schema_snapshot(data_source_id, context, db)` | 283-296 |  |
| 函数 `activate_schema_snapshot_endpoint(data_source_id, snapshot_id, context, db)` | 303-318 |  |
| 函数 `list_members(context, db)` | 322-329 |  |
| 函数 `create_invitation(request, context, db)` | 337-356 |  |
| 函数 `list_invitations(context, db)` | 360-364 |  |
| 函数 `revoke_invitation(invitation_id, context, db)` | 371-381 |  |
| 函数 `list_membership_applications_endpoint(status, context, db)` | 388-400 |  |
| 函数 `approve_membership_application_endpoint(application_id, context, db)` | 407-423 |  |
| 函数 `reject_membership_application_endpoint(application_id, context, db)` | 430-446 |  |
| 函数 `update_member(member_id, request, context, db)` | 450-486 |  |
| 函数 `reset_member_password(member_id, request, context, db) -> None` | 493-510 | Allow only a company owner to replace a non-owner member's password. |

## `backend/app/modules/organizations/connections.py`（84 行）

模块说明：Platform-registered business database connections (A11b).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConnectionNotAllowed`(ValueError) | 18-19 | The source has no usable connection of its own company. |
| 类 `ConnectionDetails`(TypedDict) | 22-28 |  |
| 函数 `new_connection(*, company_id, name, host, port, database, username, schema_name, credential_env_var, operator) -> PlatformDataConnection` | 31-56 | Build an operator-registered connection; the caller adds and commits it. |
| 函数 `resolve_connection(source) -> ConnectionDetails` | 59-84 |  |

## `backend/app/modules/organizations/data_source_policy.py`（59 行）

模块说明：Stop tenant data sources from borrowing platform secrets or reaching platform services.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `DataSourcePolicyError`(ValueError) | 16-17 | A data source points at something the platform must keep for itself. |
| 函数 `platform_setting_names() -> frozenset[str]` | 20-21 |  |
| 函数 `credential_rejection(name, *, allowlist, platform_names) -> str \| None` | 24-35 | Return why this credential name is refused, or None when it may be read. |
| 函数 `host_rejection(host, *, blocked_hosts) -> str \| None` | 38-48 |  |
| 函数 `ensure_data_source_allowed(*, credential_env_var, host) -> None` | 51-59 |  |

## `backend/app/modules/organizations/models.py`（197 行）

模块说明：Tenant, business-data-source, and discovered-schema persistence.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `Company`(Base) | 23-30 |  |
| 类 `CompanyMember`(Base) | 33-56 |  |
| 类 `CompanyInvitation`(Base) | 59-80 | A non-enumerable registration code issued by one company. |
| 类 `MembershipApplication`(Base) | 83-116 | One account's only allowed route into its designated company. |
| 类 `PlatformDataConnection`(Base) | 119-147 | A business database the platform registered for exactly one company (A11b). |
| 类 `BusinessDataSource`(Base) | 150-178 |  |
| 类 `SchemaSnapshot`(Base) | 181-197 |  |

## `backend/app/modules/organizations/repository.py`（137 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `get_company(db, *, company_id) -> Company \| None` | 13-14 |  |
| 函数 `get_membership_for_user(db, *, user_id) -> CompanyMember \| None` | 17-18 |  |
| 函数 `get_members_for_company(db, *, company_id) -> list[CompanyMember]` | 21-28 |  |
| 函数 `get_membership(db, *, company_id, user_id) -> CompanyMember \| None` | 31-38 |  |
| 函数 `get_invitation_by_hash(db, *, code_hash) -> CompanyInvitation \| None` | 41-44 |  |
| 函数 `get_invitation_for_company(db, *, invitation_id, company_id) -> CompanyInvitation \| None` | 47-55 |  |
| 函数 `get_invitations_for_company(db, *, company_id) -> list[CompanyInvitation]` | 58-67 |  |
| 函数 `get_application_for_company(db, *, application_id, company_id) -> MembershipApplication \| None` | 70-78 |  |
| 函数 `get_application_for_user(db, *, user_id) -> MembershipApplication \| None` | 81-86 |  |
| 函数 `get_applications_for_company(db, *, company_id, status) -> list[MembershipApplication]` | 89-97 |  |
| 函数 `get_data_source(db, *, data_source_id, company_id) -> BusinessDataSource \| None` | 100-108 |  |
| 函数 `get_latest_snapshot(db, *, data_source_id) -> SchemaSnapshot \| None` | 111-116 |  |
| 函数 `get_snapshot(db, *, snapshot_id, data_source_id) -> SchemaSnapshot \| None` | 119-127 |  |
| 函数 `get_snapshots(db, *, data_source_id) -> list[SchemaSnapshot]` | 130-137 |  |

## `backend/app/modules/organizations/schemas.py`（150 行）

模块说明：HTTP contracts for tenant data-source setup.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `CompanyCreate`(BaseModel) | 8-9 |  |
| 类 `CompanyOut`(BaseModel) | 12-17 |  |
| 类 `CurrentCompanyOut`(BaseModel) | 20-26 |  |
| 类 `BusinessDataSourceCreate`(BaseModel) | 29-35 | A11b: admins pick one of their company's platform-registered connections. |
| 类 `DataConnectionOut`(BaseModel) | 38-43 | What a company admin may know about a platform connection: not its address. |
| 类 `BusinessDataSourceOut`(BaseModel) | 46-54 |  |
| 类 `AssistantDataSourceOut`(BaseModel) | 57-63 | Non-sensitive data-source fields needed by the chat composer. |
| 类 `SchemaSnapshotOut`(BaseModel) | 66-74 |  |
| 类 `CompanyMemberOut`(BaseModel) | 77-87 |  |
| 类 `CompanyMemberUpdate`(BaseModel) | 90-92 |  |
| 类 `CompanyMemberPasswordReset`(BaseModel) | 95-98 | Owner-authorized password replacement; the old password is never exposed. |
| 类 `CompanyInvitationCreate`(BaseModel) | 101-103 |  |
| 类 `CompanyInvitationCreated`(BaseModel) | 106-110 |  |
| 类 `CompanyInvitationOut`(BaseModel) | 113-121 |  |
| 类 `MembershipApplicationRegister`(BaseModel) | 124-128 |  |
| 类 `MembershipApplicationReapply`(BaseModel) | 131-134 |  |
| 类 `MembershipApplicationOut`(BaseModel) | 137-146 |  |
| 类 `MembershipApplicationRegistered`(MembershipApplicationOut) | 149-150 |  |

## `backend/app/modules/organizations/service.py`（485 行）

模块说明：Transaction and authorization boundary for company setup and onboarding.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `CreatedInvitation`() | 41-43 |  |
| 类 `RegisteredApplication`() | 47-48 |  |
| 类 `BootstrappedOwner`() | 52-54 |  |
| 函数 `bootstrap_first_company_owner(db, *, name, username, password, company_name) -> BootstrappedOwner` | 57-83 | Create the only self-service owner while the platform has no company. |
| 函数 `create_company(db, *, user_id, name) -> Company` | 86-97 |  |
| 函数 `create_company_invitation(db, *, company_id, created_by_user_id, max_uses, expires_at) -> CreatedInvitation \| None` | 100-132 | Create a code whose plaintext form is returned only once. |
| 函数 `list_company_invitations(db, *, company_id) -> list[CompanyInvitation]` | 135-138 |  |
| 函数 `revoke_company_invitation(db, *, invitation_id, company_id) -> CompanyInvitation \| None` | 141-157 |  |
| 函数 `register_membership_application(db, *, name, username, password, invitation_code) -> RegisteredApplication` | 160-196 | Create an inactive account and its only company-join application. |
| 函数 `reapply_to_same_company(db, *, username, password, invitation_code) -> MembershipApplication` | 199-229 | Allow a rejected account to resubmit only to its original company. |
| 函数 `approve_membership_application(db, *, application_id, company_id, reviewer_user_id) -> MembershipApplication \| None` | 232-286 | Approve exactly one pending application in the reviewer's company. |
| 函数 `reject_membership_application(db, *, application_id, company_id, reviewer_user_id) -> MembershipApplication \| None` | 289-308 |  |
| 函数 `list_membership_applications(db, *, company_id, status) -> list[MembershipApplication]` | 311-314 |  |
| 函数 `list_data_connections(db, *, company_id) -> list[PlatformDataConnection]` | 317-326 |  |
| 类 `DataConnectionNotFound`(LookupError) | 329-330 | No connection with this id is registered for the company. |
| 函数 `create_data_source(db, *, company_id, user_id, name, connection_id) -> BusinessDataSource \| None` | 333-378 |  |
| 函数 `discover_data_source_schema(db, *, data_source_id, company_id, user_id) -> SchemaSnapshot \| None` | 381-415 |  |
| 函数 `get_current_schema_snapshot(db, *, data_source_id, company_id, user_id) -> SchemaSnapshot \| None` | 418-433 |  |
| 函数 `activate_schema_snapshot(db, *, data_source_id, company_id, user_id, snapshot_id) -> SchemaSnapshot \| None` | 436-449 |  |
| 函数 `list_company_members(db, *, company_id) -> list[CompanyMember]` | 452-453 |  |
| 函数 `reset_company_member_password(db, *, company_id, member_id, new_password) -> User \| None` | 456-485 | Replace a non-owner member password and invalidate all existing tokens. |

## `backend/app/modules/reporting/citation_validation.py`（66 行）

模块说明：引用校验器 —— 检查答案中的引用是否真实存在

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `validate_citations(answer, user_id, *, allowed_chunk_ids) -> tuple[bool, list[int]]` | 11-66 | 校验答案中的引用编号是否真实存在，且当前用户的公司角色可见。 |

## `backend/app/modules/reporting/composer.py`（209 行）

模块说明：Deterministically compose a report from already-authorized evidence.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `render_evidence_purpose(purpose) -> str` | 26-28 | Compatibility export for existing Reviewer rendering. |
| 函数 `render_data_fields(columns, row) -> str` | 31-33 | Compatibility export for existing Reviewer rendering. |
| 函数 `compose_report(*, data_result, knowledge_result, route) -> FinalAnalysisReport` | 36-80 |  |
| 函数 `_document_citations(knowledge_result, knowledge_answer) -> list[DocumentCitation]` | 83-103 |  |
| 函数 `_hypotheses(facts, citations, knowledge_answer) -> list[Hypothesis]` | 106-121 |  |
| 函数 `_document_findings(*, route, citations, knowledge_answer) -> list[DocumentFinding]` | 124-144 | Prepare a candidate finding; Reviewer grants publication after semantic review. |
| 函数 `_limitations(*, facts, citations, route, data_failed, knowledge_failed) -> list[Limitation]` | 147-174 |  |
| 函数 `_recommendations(facts, hypotheses) -> list[Recommendation]` | 177-191 |  |
| 函数 `_summary(status, facts, document_findings, hypotheses, limitations) -> str` | 194-209 |  |

## `backend/app/modules/reporting/coverage.py`（53 行）

模块说明：覆盖率计算器 —— 检查证据是否覆盖了问题的关键实体

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_extract_keywords(question) -> list[str]` | 6-20 | Small local extractor so coverage is independent from RAG internals. |
| 函数 `calculate_coverage(question, evidences, answer) -> tuple[float, list[str]]` | 23-53 | 计算证据对问题关键实体的覆盖率。返回(覆盖率, 未覆盖实体列表) |

## `backend/app/modules/reporting/numeric_validation.py`（110 行）

模块说明：数字校验器 —— 防止答案把接近但不同的 SQL 数值说成事实。

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_numbers_from_value(value) -> list[Decimal]` | 12-21 |  |
| 函数 `_display_matches_source(answer_number, *, has_percent_sign, source_numbers) -> bool` | 24-48 | Allow only exact values or the rounding implied by the displayed precision. |
| 函数 `_without_trusted_evidence_labels(answer, data_result) -> str` | 51-62 | Exclude only deterministic query labels, never their returned values. |
| 函数 `validate_numbers(answer, data_result, *, knowledge_evidences) -> tuple[bool, list[str]]` | 65-110 | Validate values against controlled SQL rows or cited retrieved text. |

## `backend/app/modules/reporting/qualification.py`（72 行）

模块说明：Number source sentences so a reviewer points at a boundary instead of copying it.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `number_sentences(evidences) -> dict[str, tuple[int, str]]` | 14-25 | Map "chunk_id.n" to that chunk's n-th sentence, counted from 1. |
| 函数 `global_references(evidences) -> dict[str, tuple[int, str]]` | 28-37 | Number every sentence of all evidences S1, S2, … in evidence order. |
| 函数 `with_numbered_sentences(evidences) -> list[dict]` | 40-51 | The same evidences, each sentence prefixed by its reference. |
| 函数 `resolve_references(references, evidences) -> tuple[list[DocumentQualificationReview], int]` | 54-72 | The referenced sentences, and how many references matched nothing. |

## `backend/app/modules/reporting/reviewer_agent.py`（723 行）

模块说明：Reviewer Agent —— 检查数据一致性和建议合理性，不替代确定性校验器

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_format_data_result(data_result) -> str \| None` | 34-65 |  |
| 函数 `_review_metadata(report, **metadata) -> dict` | 68-73 | Keep legacy reviewer metadata while exposing the structured report. |
| 函数 `_validate_final_answer(*, answer, question, user_id, data_result, knowledge_evidences, citation_validator) -> tuple[bool, dict]` | 76-127 | Run deterministic guards after composition, before exposing model-derived text. |
| 函数 `_safe_validation_failure_answer(data_summary) -> str` | 130-133 |  |
| 函数 `_unsupported_claim_reason(data_result) -> str \| None` | 136-146 |  |
| 函数 `_semantic_limitations(review) -> list[Limitation]` | 149-168 |  |
| 函数 `_supported_document_chunks(*, plan, semantic_review, retrieved_chunk_ids) -> set[int] \| None` | 171-185 |  |
| 函数 `_is_document_question(plan) -> bool` | 188-190 |  |
| 函数 `_verbatim_document_qualifications(*, semantic_review, supported_chunk_ids, knowledge_evidences) -> list[DocumentQualification]` | 193-238 | Retain only review boundaries that are verbatim in cited retrieved text. |
| 类 `ReviewerAgent`(Agent) | 241-723 | 检查多个 Agent 的结果是否存在冲突，不直接生成新结论 |
| 函数 `ReviewerAgent.__init__(semantic_reviewer, *, citation_validator) -> None` | 244-251 |  |
| 函数 `ReviewerAgent.set_citation_validator(validator) -> None` | 253-257 | Attach the database-backed ownership check at the workflow boundary. |
| 函数 `ReviewerAgent.name() -> str` | 260-261 |  |
| 函数 `ReviewerAgent.description() -> str` | 264-265 |  |
| 函数 `ReviewerAgent.allowed_tools() -> list[Tool]` | 268-269 |  |
| 函数 `ReviewerAgent.run(input) -> AgentOutput` | 271-723 | 对比 context 中的两份证据，检查一致性 |

## `backend/app/modules/reporting/schema_validation.py`（45 行）

模块说明：格式校验器 —— 检查答案是否符合基本格式约定

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `validate_schema(answer, evidence_count, *, citation_required) -> tuple[bool, list[str]]` | 4-45 | 检查答案的格式是否符合基本约定。 |

## `backend/app/modules/reporting/schemas.py`（216 行）

模块说明：Persistable, evidence-bound contract for a business analysis response.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConfirmedFact`(BaseModel) | 8-11 |  |
| 类 `Hypothesis`(BaseModel) | 14-26 |  |
| 函数 `Hypothesis.requires_document_or_attachment_evidence() -> 'Hypothesis'` | 23-26 |  |
| 类 `Recommendation`(BaseModel) | 29-42 |  |
| 函数 `Recommendation.requires_a_basis() -> 'Recommendation'` | 39-42 |  |
| 类 `DataEvidence`(BaseModel) | 45-52 |  |
| 类 `MetricAssessment`(BaseModel) | 55-62 |  |
| 类 `ClaimAssessment`(BaseModel) | 65-67 |  |
| 类 `DocumentCitation`(BaseModel) | 70-74 |  |
| 类 `DocumentQualification`(BaseModel) | 77-81 | A verbatim, citation-bound boundary on a document finding. |
| 类 `DocumentFinding`(BaseModel) | 84-90 | A directly supported document fact, distinct from a data-backed fact. |
| 函数 `build_attachment_citation_id(*, artifact_version_id, parse_result_id, char_start, char_end, fragment_sha256) -> str` | 93-105 | Return the deterministic identity for one immutable parsed-text span. |
| 类 `AttachmentCitation`(BaseModel) | 108-135 | A storage-verifiable attachment span; extracted text is never persisted here. |
| 函数 `AttachmentCitation.validates_identity_and_range() -> 'AttachmentCitation'` | 123-135 |  |
| 类 `Limitation`(BaseModel) | 138-141 |  |
| 类 `FinalAnalysisReport`(BaseModel) | 144-216 |  |
| 函数 `FinalAnalysisReport.validate_evidence_contract() -> 'FinalAnalysisReport'` | 160-216 |  |

## `backend/app/modules/reporting/semantic_review.py`（38 行）

模块说明：Structured model-review contracts for plans, SQL candidates, and evidence.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SQLSemanticReview`(BaseModel) | 8-11 |  |
| 类 `DocumentQualificationReview`(BaseModel) | 14-18 | One exact source boundary proposed by semantic review. |
| 类 `ContradictedMemory`(BaseModel) | 21-23 |  |
| 类 `EvidenceSemanticReview`(BaseModel) | 26-38 |  |

## `backend/app/modules/reporting/semantic_review_service.py`（466 行）

模块说明：Model-backed semantic checks; they never grant permissions or execute SQL.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_catalog_payload(catalog, shown) -> dict[str, Any]` | 63-78 |  |
| 函数 `_filter_values(catalog, shown) -> dict[str, Any]` | 81-92 |  |
| 函数 `_tables_in_sql(sql) -> set[str] \| None` | 95-103 | Tables the SQL reads; None when it cannot be parsed, so nothing is hidden. |
| 函数 `_complete_plan_output(raw_output) -> str` | 106-123 | An omitted nullable field means null; PlannerDecision still checks the rest. |
| 函数 `_numbers(text) -> set[str]` | 126-127 |  |
| 函数 `_credible_memory_flags(review, memories_used, data_result, knowledge_result) -> list[Any]` | 130-162 | Code's last word on the model's suspicions, since a prompt cannot promise. |
| 函数 `_review_context(policy, system_prompt, payload) -> tuple[dict[str, Any], ContextManifest \| None]` | 165-186 | The payload to send and the manifest the ledger records with it (C5). |
| 函数 `_evidence_context(system_prompt, sections) -> tuple[dict[str, Any], ContextManifest \| None]` | 189-214 | The evidence review's payload and the manifest recorded with it (C5d). |
| 类 `SemanticReviewService`() | 217-466 | Use a model as a semantic critic over already-scoped inputs. |
| 函数 `SemanticReviewService.__init__(gateway, *, sleeper) -> None` | 220-228 |  |
| 函数 `SemanticReviewService.review_plan(*, question, proposed_plan, catalog) -> PlannerDecision` | 230-275 |  |
| 函数 `SemanticReviewService._review_plan_once(system_prompt, payload, proposed_plan) -> PlannerDecision` | 277-296 |  |
| 函数 `SemanticReviewService._preserved_plan_from_review(raw_output, proposed_plan) -> PlannerDecision \| None` | 299-311 | Accept common critic vocabulary as an explicit keep-plan decision. |
| 函数 `SemanticReviewService.review_sql(*, question, plan, candidate, catalog) -> SQLSemanticReview` | 313-347 |  |
| 函数 `SemanticReviewService._review_sql_once(system_prompt, payload) -> SQLSemanticReview` | 349-361 |  |
| 函数 `SemanticReviewService.review_evidence(*, question, plan, data_result, knowledge_result, report, memories_used) -> EvidenceSemanticReview` | 363-427 |  |
| 函数 `SemanticReviewService._parse_with_repair(model, raw_output, error_message, system_prompt, payload, normalize)` | 429-451 |  |
| 函数 `SemanticReviewService._chat(*, system_prompt, payload) -> str` | 453-466 |  |

## `backend/app/modules/reporting/validation.py`（38 行）

模块说明：Final deterministic gate before a report may be persisted or published.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ReportValidationError`(ValueError) | 10-11 |  |
| 函数 `validate_report(draft, *, allowed_chunk_ids, allowed_attachment_citation_ids) -> FinalAnalysisReport` | 14-38 | Validate schema links and the task-frozen citation scope without an LLM. |

## `backend/app/modules/reviews/api.py`（125 行）

模块说明：Company-admin review endpoints for reports held before publication.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_review_request_out(record) -> ReviewRequestOut` | 21-43 |  |
| 函数 `list_review_requests_endpoint(request_status, context, db)` | 47-64 | Return only this company's review queue, newest first. |
| 函数 `approve_review_request_endpoint(request_id, payload, context, db)` | 72-97 |  |
| 函数 `reject_review_request_endpoint(request_id, payload, context, db)` | 101-125 |  |

## `backend/app/modules/reviews/models.py`（52 行）

模块说明：Durable human-review requests for reports that must not auto-publish.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ReviewRequest`(Base) | 14-52 |  |

## `backend/app/modules/reviews/schemas.py`（44 行）

模块说明：HTTP contracts for bounded human review decisions.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ReviewDecisionIn`(BaseModel) | 23-24 |  |
| 类 `ReviewDecisionOut`(BaseModel) | 27-31 |  |
| 类 `ReviewRequestOut`(BaseModel) | 34-44 | Safe queue item for a company administrator's review workspace. |

## `backend/app/modules/reviews/service.py`（138 行）

模块说明：Deterministic human-review policy and approval state transitions.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ApprovedReviewBundle`() | 19-21 |  |
| 函数 `requires_human_review(report) -> bool` | 24-26 | Only a deterministic policy, never the Reviewer model, gates publishing. |
| 函数 `create_review_request(db, *, task, reason_code) -> ReviewRequest` | 29-40 |  |
| 函数 `approve_review_request(db, *, request_id, company_id, reviewer, note) -> ApprovedReviewBundle \| None` | 43-93 |  |
| 函数 `reject_review_request(db, *, request_id, company_id, reviewer, note) -> AnalysisTask \| None` | 96-138 |  |

## `backend/app/modules/runtime/context/compressors.py`（127 行）

模块说明：Section compressors (C4): code only, so nothing is reworded.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `compress_history(conversation_context) -> Any` | 21-49 | Shorten older assistant replies; never drop or cut what the user said. |
| 函数 `_is_long_reply(message) -> bool` | 52-56 |  |
| 函数 `split_sentences(text) -> list[str]` | 67-69 | The text's sentences with their own punctuation; they join back to it. |
| 函数 `question_terms(question) -> tuple[set[str], set[str]]` | 72-75 | (words, entity codes) from the question, both lower case. |
| 函数 `sentence_score(sentence, *, terms, entities) -> int` | 78-90 | How much of the question one evidence sentence speaks to. |
| 函数 `excerpt(text, question, max_chars) -> str \| None` | 93-114 | The question's sentences from ``text`` within ``max_chars``, or None. |
| 函数 `_join(sentences, kept) -> str` | 117-127 |  |

## `backend/app/modules/runtime/context/engine.py`（235 行）

模块说明：Build what one model call may see, and say plainly when it does not fit (C4).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `SectionRule`() | 33-42 |  |
| 类 `ContextPolicy`() | 46-60 |  |
| 函数 `ContextPolicy.available_tokens() -> int` | 59-60 |  |
| 类 `ContextBuild`() | 64-72 |  |
| 函数 `ContextBuild.fits() -> bool` | 71-72 |  |
| 类 `ContextBudgetExceeded`(Exception) | 75-84 | Raised before any model budget is reserved, so nothing is charged. |
| 函数 `ContextBudgetExceeded.__init__(build) -> None` | 78-84 |  |
| 函数 `count_tokens(value) -> int` | 87-89 |  |
| 函数 `build_context(policy, sections) -> ContextBuild` | 92-171 | The payload this policy allows, what was done to it, and whether it fits. |
| 函数 `require_fit(build) -> dict[str, Any]` | 174-178 | The payload to send, or ContextBudgetExceeded: never an over-budget call. |
| 函数 `_manifest(policy, sections, payload, *, filtered, compressed, capped, dropped, tokens, over_budget) -> ContextManifest` | 181-235 | Per section, in the order received: tokens given, tokens sent, and why. |

## `backend/app/modules/runtime/context/manifest.py`（64 行）

模块说明：The ledger record of how a model call's context was built (C3).

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `content_hash(value) -> str` | 22-25 | Same value, same hash, whatever the key order. |
| 类 `SectionEntry`() | 29-36 |  |
| 类 `ContextManifest`() | 40-64 |  |
| 函数 `ContextManifest.to_record() -> dict[str, Any]` | 47-64 |  |

## `backend/app/modules/runtime/context_budget.py`（148 行）

模块说明：Decide what each model call may see, and shrink it when it gets close to full.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ContextDecision`() | 39-46 |  |
| 函数 `cap_data_rows(data_result) -> dict` | 49-62 | Keep the first rows and say how many were dropped; the columns stay. |
| 函数 `cap_chunk_text(knowledge_result) -> dict` | 65-78 | Shorten long chunks and mark them, so a model can't read absence as fact. |
| 函数 `assemble(policy, sections) -> tuple[dict[str, Any], ContextDecision]` | 81-108 | The payload a node may send, and a record of what was done to it. |

## `backend/app/modules/runtime/context_measurement.py`（127 行）

模块说明：C2: measure what every model call carries, without changing any call.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `declare_sections(**sections) -> None` | 34-36 | Call right before one model call: each prompt part's name and text. |
| 函数 `take_declared_sections() -> dict[str, str] \| None` | 39-47 | The sections declared for the call being made, then forget them. |
| 函数 `context_usage(sections, fallback) -> dict[str, Any]` | 50-66 | What reserve_model_call stores under resource_usage["context_tokens"]. |
| 函数 `gateway_sections(prompt, system_prompt, messages, tools) -> dict[str, str]` | 69-103 | The sections a gateway can see in one request (C2 fallback). |
| 函数 `measure_sections(sections) -> dict[str, int]` | 106-118 | Token count per section name, plus "total" for the sum. |
| 函数 `measurement_details(node, sections) -> dict[str, Any]` | 121-127 | The ``details`` payload for append_workflow_event(event_type="context_measured"). |

## `backend/app/modules/runtime/model_governance.py`（583 行）

模块说明：Task-scoped model budget enforcement and privacy-safe call auditing.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ModelBudgetExceeded`(RuntimeError) | 35-38 | Stable, non-retryable signal: a task has exhausted its model allowance. |
| 类 `ModelCallCancelled`(RuntimeError) | 41-44 | Do not start another model operation after task cancellation. |
| 函数 `frozen_max_output_tokens(default) -> int` | 50-56 | Use the task's frozen output reservation when a governed call is active. |
| 函数 `frozen_timeout_seconds(default) -> int` | 59-69 | Use the task's bounded provider timeout while a governed call is active. |
| 函数 `estimate_chat_prompt_tokens(token_counter, prompt, system_prompt) -> int` | 72-81 | Reserve user and system content plus conservative chat-message framing. |
| 类 `ModelCallScope`() | 85-99 |  |
| 函数 `model_context_scope(manifest) -> Iterator[None]` | 112-118 | Every call reserved inside (a repair included) records this manifest. |
| 函数 `model_call_scope(db, *, task, attempt, node_name, prompt_version, is_repair) -> Iterator[None]` | 122-144 |  |
| 函数 `model_node_scope(node_name, *, is_repair) -> Iterator[None]` | 148-166 |  |
| 函数 `fallback_chain_scope(initial_model) -> Iterator[None]` | 170-179 | Keep a bounded fallback chain within one logical gateway request. |
| 函数 `next_fallback_model(current_model) -> str \| None` | 182-197 | Return the next frozen fallback after a retryable provider failure only. |
| 函数 `_decimal(value) -> Decimal \| None` | 200-204 |  |
| 函数 `_price_for_call(policy, *, provider, model_name, parameters) -> tuple[str \| None, str \| None, Decimal \| None, Decimal \| None]` | 207-250 | Match a frozen provider/model/parameter price entry, if one exists. |
| 函数 `_priced_cost(*, prompt_tokens, completion_tokens, prompt_price, completion_price) -> Decimal \| None` | 253-265 |  |
| 函数 `reserve_model_call(*, provider, model_name, estimated_prompt_tokens, reserved_completion_tokens, pricing_parameters, charge_kind, request_parts) -> ModelCallScope \| None` | 268-401 | Atomically consume a call slot before contacting an external provider. |
| 函数 `reserve_local_resource_call(*, resource_kind, model_name, resource_usage) -> ModelCallScope \| None` | 404-452 | Persist a local embedding/rerank operation before execution. |
| 函数 `record_model_call(scope, *, provider, model_name, prompt_tokens, completion_tokens, duration_ms, result_category, error_code, prompt_template_id, prompt_hash, model_parameters, resource_usage) -> None` | 455-555 |  |
| 函数 `prompt_provenance(prompt, system_prompt, *, json_mode, timeout_seconds, temperature, max_output_tokens) -> dict` | 558-583 | Return privacy-safe identifiers for the exact model request content. |

## `backend/app/modules/runtime/prompts.py`（101 行）

模块说明：Versioned system prompts read from app/prompts/ (G1).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `PromptRegistryError`(RuntimeError) | 25-26 |  |
| 类 `PromptEntry`() | 30-35 |  |
| 函数 `_read_text(path) -> str` | 38-42 |  |
| 类 `PromptRegistry`() | 45-96 |  |
| 函数 `PromptRegistry.__init__(entries) -> None` | 46-53 |  |
| 函数 `PromptRegistry.load(directory) -> PromptRegistry` | 56-82 |  |
| 函数 `PromptRegistry.render(prompt_id, **variables) -> str` | 84-90 |  |
| 函数 `PromptRegistry.text(prompt_id) -> str` | 92-93 |  |
| 函数 `PromptRegistry.version_of(prompt_id) -> str` | 95-96 |  |
| 函数 `get_prompt_registry() -> PromptRegistry` | 100-101 |  |

## `backend/app/modules/runtime/schemas.py`（62 行）

模块说明：Frozen, machine-enforced contracts for workflow tool access.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RAGSearchInputSchema`(BaseModel) | 7-19 |  |
| 函数 `RAGSearchInputSchema._omit_absent_window(handler)` | 15-19 |  |
| 类 `SQLQueryInputSchema`(BaseModel) | 22-23 |  |
| 类 `TemplateQueryInputSchema`(DataRequest) | 26-27 | Runtime contract for the registered-query tool. |
| 类 `ToolPolicy`(BaseModel) | 30-50 | The allowlist and scope rules frozen when an analysis task is created. |
| 函数 `ToolPolicy.no_empty_or_duplicate_tool_names(value) -> tuple[str, ...]` | 41-50 |  |
| 类 `ToolBudget`(BaseModel) | 53-57 | Bound each task before a Tool is invoked, rather than after damage is done. |
| 类 `ToolBudgetUsage`(BaseModel) | 60-62 |  |

## `backend/app/modules/runtime/tool_guard.py`（245 行）

模块说明：What protects a tool from its own outages: retries, a circuit breaker, a switch.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `is_infrastructure_failure(output) -> bool` | 48-58 | True when the tool, not the request, is what failed. |
| 函数 `outcome_of_failure(output) -> Outcome` | 61-73 | How a tool's failure counts in the tool loop. |
| 类 `BreakerStore`(Protocol) | 76-83 |  |
| 函数 `BreakerStore.incr(key) -> int` | 77-77 |  |
| 函数 `BreakerStore.expire(key, seconds) -> object` | 78-78 |  |
| 函数 `BreakerStore.set(key, value, *, nx, ex) -> object` | 79-81 |  |
| 函数 `BreakerStore.exists(key) -> int` | 82-82 |  |
| 函数 `BreakerStore.delete(*keys) -> object` | 83-83 |  |
| 类 `CircuitBreaker`() | 86-154 | Open after repeated failures, then let one call test whether it recovered. |
| 函数 `CircuitBreaker.__init__(key, store, *, threshold, window_seconds, cooldown_seconds, probe_seconds) -> None` | 94-109 |  |
| 函数 `CircuitBreaker._safely(action, fallback) -> object` | 111-116 |  |
| 函数 `CircuitBreaker.before_call() -> Literal['closed', 'probe', 'open']` | 118-129 |  |
| 函数 `CircuitBreaker.record_success() -> None` | 131-139 |  |
| 函数 `CircuitBreaker.record_failure() -> None` | 141-154 |  |
| 类 `GuardedTool`(Tool) | 157-200 | Retry outages with backoff, and stop calling a tool that keeps failing. |
| 函数 `GuardedTool.__init__(tool, breaker, *, retries, backoff_seconds, sleep) -> None` | 160-173 |  |
| 函数 `GuardedTool.name() -> str` | 176-177 |  |
| 函数 `GuardedTool.description() -> str` | 180-181 |  |
| 函数 `GuardedTool.execute(input) -> ToolOutput` | 183-200 |  |
| 类 `FallbackTool`(Tool) | 203-230 | Switch to a tool of the same kind when the first one is out of service. |
| 函数 `FallbackTool.__init__(primary, secondary) -> None` | 206-208 |  |
| 函数 `FallbackTool.name() -> str` | 211-212 |  |
| 函数 `FallbackTool.description() -> str` | 215-216 |  |
| 函数 `FallbackTool.execute(input) -> ToolOutput` | 218-230 |  |
| 函数 `redis_breaker_store() -> BreakerStore` | 233-245 |  |

## `backend/app/modules/runtime/tool_loop.py`（240 行）

模块说明：The loop that lets a model choose tools, with every limit held by code.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ToolSpec`() | 38-64 | One entry of the tool catalog: what the model reads, and its parameter contract. |
| 函数 `ToolSpec.to_openai() -> dict` | 50-64 |  |
| 类 `ToolReply`() | 68-73 | What a handler decided: what the model sees, and how the outcome counts. |
| 函数 `_setting(name) -> Callable[[], Any]` | 76-77 |  |
| 类 `LoopLimits`() | 81-91 | Defaults come from the TOOL_LOOP_* settings (K1). |
| 类 `LoopResult`() | 95-99 |  |
| 函数 `_parse_arguments(call, spec) -> BaseModel \| ToolReply` | 111-130 |  |
| 函数 `_call_model(gateway, messages, tools, limits, sleep)` | 133-147 |  |
| 函数 `run_tool_loop(gateway, *, system_prompt, user_prompt, specs, handlers, limits, clock, sleep) -> LoopResult` | 150-240 | Run until a handler finishes, the model stops, or a code-held limit is hit. |

## `backend/app/modules/runtime/tool_runtime.py`（471 行）

模块说明：Single execution boundary for workflow tools.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `deny_message(code) -> str` | 56-57 |  |
| 类 `ToolRuntimeContext`() | 61-64 |  |
| 类 `RuntimeTool`(Tool) | 67-86 | Adapter that preserves the existing Tool protocol for Agents. |
| 函数 `RuntimeTool.__init__(runtime, tool) -> None` | 70-72 |  |
| 函数 `RuntimeTool.name() -> str` | 75-76 |  |
| 函数 `RuntimeTool.description() -> str` | 79-80 |  |
| 函数 `RuntimeTool.execute(input) -> ToolOutput` | 82-86 |  |
| 类 `ToolRuntime`() | 89-471 | Enforce frozen scope and emit a redacted audit trail around every Tool. |
| 函数 `ToolRuntime.__init__(*, db, attempt, context) -> None` | 92-103 |  |
| 函数 `ToolRuntime.wrap(tool) -> RuntimeTool` | 105-106 |  |
| 函数 `ToolRuntime.resolve_empty_document_scope(tool, input) -> ToolOutput \| None` | 108-144 | Resolve an authorized no-resource case without executing a search. |
| 函数 `ToolRuntime._tool_contract_version(tool) -> str` | 147-149 |  |
| 函数 `ToolRuntime._deny(tool, code, details) -> ToolOutput` | 151-174 |  |
| 函数 `ToolRuntime._validate_scope(tool, input, policy) -> ToolOutput \| None` | 176-200 |  |
| 函数 `ToolRuntime._validate_current_authorization(tool) -> ToolOutput \| None` | 202-225 | Intersect frozen task scope with the initiator's current membership. |
| 函数 `ToolRuntime._runtime_mcp_context(input) -> dict[str, object]` | 227-264 | Attach a Runtime-owned, request-specific binding for trusted MCP. |
| 函数 `ToolRuntime._validate_current_document_scope(tool, input) -> ToolOutput \| None` | 266-300 | Require frozen RAG documents to remain visible to the initiator. |
| 函数 `ToolRuntime._validate_input(tool, input) -> ToolInput \| ToolOutput` | 302-327 |  |
| 函数 `ToolRuntime._with_server_parameters(tool, input, policy) -> ToolInput` | 329-348 | Attach policy-only controls after untrusted input was normalized. |
| 函数 `ToolRuntime._task() -> AnalysisTask` | 350-354 |  |
| 函数 `ToolRuntime._reserve_call(tool) -> ToolOutput \| None` | 356-370 |  |
| 函数 `ToolRuntime.execute(tool, input) -> ToolOutput` | 372-384 |  |
| 函数 `ToolRuntime._execute(tool, input) -> ToolOutput` | 386-471 |  |

## `backend/app/modules/workflow/api.py`（74 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `create_task(request_model, current_user, db)` | 22-35 | 创建分析任务（异步执行） |
| 函数 `list_tasks(current_user, db)` | 39-44 | 查询当前用户的所有任务 |
| 函数 `get_task(task_id, current_user, db)` | 48-59 | 查询单个任务详情 |
| 函数 `cancel_task(task_id, current_user, db)` | 63-74 |  |

## `backend/app/modules/workflow/audit/events.py`（59 行）

模块说明：Safe append-only audit event helpers.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `append_workflow_event(db, *, attempt, company_id, event_type, node_name, tool_name, status, error_code, duration_ms, details) -> WorkflowEvent` | 14-59 | Append metadata only; callers must never pass prompts, SQL, or document text. |

## `backend/app/modules/workflow/audit/events_models.py`（51 行）

模块说明：Append-only audit records for workflow and tool execution.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `WorkflowEvent`(Base) | 16-51 | A durable, redacted event; it is not used to reconstruct workflow state. |

## `backend/app/modules/workflow/audit/model_call.py`（75 行）

模块说明：Privacy-safe audit metadata for one governed model invocation.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ModelCallRecord`(Base) | 18-75 |  |

## `backend/app/modules/workflow/audit/tool_call.py`（44 行）

模块说明：Privacy-safe audit metadata for one governed Tool invocation.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ToolCallRecord`(Base) | 16-44 |  |

## `backend/app/modules/workflow/delivery/outbox.py`（332 行）

模块说明：Reliable publication for analysis task outbox events.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ClaimedAnalysisTaskPublication`() | 24-28 |  |
| 函数 `create_analysis_task_event(db, *, task_id) -> AnalysisTaskOutboxEvent` | 31-40 |  |
| 函数 `publish_analysis_task_event(db, *, event_id, enqueue) -> bool` | 43-98 | Publish one claimed event; broker acceptance is not Worker delivery. |
| 函数 `pending_event_ids(db, *, limit) -> list[int]` | 101-124 |  |
| 函数 `claim_analysis_task_event_for_publication(db, *, event_id, lease_seconds) -> ClaimedAnalysisTaskPublication \| None` | 127-173 |  |
| 函数 `mark_analysis_task_event_broker_accepted(db, *, claim, broker_message_id) -> bool` | 176-210 |  |
| 函数 `return_analysis_task_event_to_pending(db, *, claim, failure_code) -> bool` | 213-237 |  |
| 函数 `mark_analysis_task_event_worker_claimed(db, *, task_id, execution_id) -> bool` | 243-264 |  |
| 函数 `settle_redelivered_analysis_task_events(db, *, task_id, execution_id) -> bool` | 267-293 | Close unclaimed events of a task that a redelivery found unclaimable. |
| 函数 `cancel_unclaimed_analysis_task_event(db, *, task_id) -> bool` | 296-314 | Make cancellation terminal for an event that has no effective Worker claim. |
| 函数 `reconcile_unclaimed_broker_accepted_events(db, *, limit) -> list[int]` | 317-332 |  |

## `backend/app/modules/workflow/delivery/outbox_models.py`（70 行）

模块说明：Transactional events used to reliably publish analysis tasks.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisTaskOutboxEvent`(Base) | 22-70 |  |

## `backend/app/modules/workflow/lifecycle/capacity.py`（114 行）

模块说明：Fail-closed capacity admission from an authenticated local volume signal.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `require_task_capacity(settings) -> None` | 21-39 | Reject new work if the configured persistent-volume signal is unsafe. |
| 函数 `_read_capacity_signal(settings) -> dict[str, object]` | 42-80 |  |
| 函数 `_validated_available_bytes(payload, *, settings) -> int` | 83-114 |  |

## `backend/app/modules/workflow/lifecycle/checkpoint.py`（51 行）

模块说明：Recoverable, ordered workflow snapshots for one execution attempt.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `WorkflowCheckpoint`(Base) | 17-51 |  |

## `backend/app/modules/workflow/lifecycle/execution.py`（941 行）

模块说明：Atomic execution ownership and durable workflow checkpoints.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `execution_heartbeat_interval_seconds() -> int` | 37-39 | Renew well before expiry without adding another runtime setting. |
| 类 `ClaimedExecution`() | 43-47 |  |
| 函数 `_append_checkpoint(db, *, attempt, sequence, completed_node, next_node, state_patch, error_code, recovery_instruction, timestamp) -> WorkflowCheckpoint` | 50-78 | Persist a checkpoint and atomically advance the attempt's liveness pointer. |
| 函数 `_task_input_fingerprint(db, *, task_id) -> str` | 81-116 | Hash the frozen task contract required to safely reuse a checkpoint. |
| 函数 `_latest_resume_checkpoint(db, *, task_id, excluding_attempt_id) -> WorkflowCheckpoint \| None` | 119-140 | Return only a completed-node snapshot, never an enter-stage marker. |
| 函数 `_resume_checkpoint_rejection_reason(db, *, task_id, excluding_attempt_id) -> str \| None` | 143-170 | Explain why the newest resumable-looking snapshot is unsafe to reuse. |
| 函数 `_latest_stateful_checkpoint_for_attempt(db, *, attempt_id) -> WorkflowCheckpoint \| None` | 173-186 | Return the last durable graph snapshot from one specific prior attempt. |
| 函数 `_latest_stateful_checkpoint_before(db, *, attempt_id, before_checkpoint_id) -> WorkflowCheckpoint \| None` | 189-203 | Return the prior trusted snapshot, excluding a failed node's own output. |
| 函数 `retry_resume_node(db, *, attempt) -> str \| None` | 206-217 | Read the node whose execution was last entered by this attempt. |
| 函数 `_retry_resume_state(db, *, failed_attempt_id, failed_node, error_code, retry_number) -> dict \| None` | 220-255 | Recover before one failed node, retaining only earlier trusted state. |
| 函数 `_settle_redelivered_events(db, *, task) -> None` | 258-276 | Stop republishing events whose delivery reached an unclaimable task. |
| 函数 `claim_execution(db, *, task_id, celery_task_id, worker_id) -> ClaimedExecution \| None` | 279-451 | Claim queued/retrying work; only one delivery can create an attempt. |
| 函数 `owns_execution(db, *, task_id, execution_id) -> bool` | 454-464 |  |
| 函数 `renew_execution_lease(db, *, task_id, execution_id) -> bool` | 467-505 | Extend a still-live execution lease from a dedicated Worker Session. |
| 函数 `checkpoint_stage(db, *, attempt, stage, completed_node) -> bool` | 508-544 | Persist progress only while this execution still owns the task. |
| 函数 `checkpoint_workflow_state(db, *, attempt, stage, completed_node, next_node, workflow_state) -> bool` | 547-588 | Durably save safe node output while this Worker still owns the task. |
| 函数 `finish_execution(db, *, attempt, task_status, attempt_status, result_summary, result_data, error_message) -> bool` | 591-682 | Persist a terminal result or review hold only while ownership is current. |
| 函数 `transition_execution(db, *, attempt, task_status, stage, attempt_status, error_type, error_message, recovery_instruction, next_node, retry_error_code) -> AnalysisTask \| None` | 685-768 | Atomically relinquish an execution after a retry or failure. |
| 函数 `recover_expired_executions(db, *, now) -> list[int]` | 771-838 | Release only still-owned expired attempts for a fresh Worker claim. |
| 函数 `stranded_retrying_task_ids(db, *, older_than, limit, now) -> list[int]` | 841-861 | Find retrying work nobody holds: recovery committed it but delivery was lost. |
| 函数 `settle_stranded_task(db, *, task_id, max_redeliveries, max_stranded, now) -> Literal['redeliver', 'exhausted', 'claimed']` | 867-941 | Count one more redelivery, or fail a task that stayed stranded too long. |

## `backend/app/modules/workflow/lifecycle/execution_attempt.py`（72 行）

模块说明：Durable ownership records for individual Worker executions.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `TaskExecutionAttempt`(Base) | 17-72 |  |

## `backend/app/modules/workflow/lifecycle/model_budget.py`（51 行）

模块说明：Server-owned, task-frozen model budget policy.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `configured_model_budget(settings, *, state_extract, summary) -> dict[str, int \| str]` | 16-51 | Build the JSON-safe budget copied into every newly created task. |

## `backend/app/modules/workflow/lifecycle/publication.py`（84 行）

模块说明：Map workflow completion facts to task status and report-publication state.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `CompletionDecision`() | 20-32 |  |
| 函数 `CompletionDecision.publication_record() -> dict[str, str]` | 27-32 |  |
| 函数 `decide_completion(*, final_answer, terminal_outcome, review_status, report, company_id) -> CompletionDecision` | 35-84 | Keep worker completion separate from publication of a validated report. |

## `backend/app/modules/workflow/lifecycle/recovery.py`（111 行）

模块说明：Explicit recovery decisions for retrying a workflow node safely.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `RecoveryDecision`(BaseModel) | 10-15 | Describe the smallest safe replay boundary after a retryable failure. |
| 函数 `recovery_decision_for_node(node_name) -> RecoveryDecision \| None` | 100-102 | Return an allow-listed recovery policy; never infer graph topology at runtime. |
| 函数 `apply_recovery_decision(state, decision) -> dict` | 105-111 | Remove all invalid outputs before a graph resumes from the selected node. |

## `backend/app/modules/workflow/lifecycle/task_spec.py`（7 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `TaskSpec`(Base) | 5-7 |  |

## `backend/app/modules/workflow/lifecycle/task_state.py`（29 行）

模块说明：The only allowed AnalysisTask status transitions.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `require_task_transition(current, target) -> None` | 27-29 |  |

## `backend/app/modules/workflow/lifecycle/versioning.py`（77 行）

模块说明：Frozen workflow-release selection and safe retry rollback.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `WorkflowRollbackError`(ValueError) | 15-16 | A release change is unsafe for the task's current lifecycle state. |
| 函数 `workflow_policy_snapshot(version) -> dict` | 19-25 |  |
| 函数 `effective_workflow_version(task) -> str` | 28-33 |  |
| 函数 `rollback_task_workflow_version(db, *, task_id, target_version) -> AnalysisTask` | 36-77 | Route only a not-running retry to a verified version. |

## `backend/app/modules/workflow/models.py`（276 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `AnalysisTask`(Base) | 28-231 |  |
| 函数 `AnalysisTask.report() -> dict[str, Any] \| None` | 226-231 | Return the stable, client-facing report without exposing workflow layout. |
| 类 `AnalysisTaskDocument`(Base) | 234-242 |  |
| 类 `AnalysisTaskInputArtifactVersion`(Base) | 245-260 | An immutable attachment-version scope frozen for one analysis task. |

## `backend/app/modules/workflow/orchestration/graph.py`（293 行）

模块说明：LangGraph 工作流图 —— 把 Agent 节点串成可执行的工作流

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_traced(name, node) -> Callable` | 40-48 | O1: a span around each node; the node itself is unchanged. |
| 函数 `_route_from_start(state) -> str` | 51-54 | Resume only an allow-listed graph node from a database checkpoint. |
| 函数 `_route_after_planner(state) -> Literal['data_node', 'knowledge_node', 'planner_terminal_node', 'planning_failure_node']` | 57-82 | Route valid Planner decisions; never send an invalid plan to an Agent. |
| 函数 `_route_after_data(state) -> Literal['knowledge_node', 'reviewer_node']` | 85-90 | Continue to knowledge only for an LLM-approved hybrid plan. |
| 函数 `_route_after_smart_router(state) -> Literal['data_node', 'knowledge_node', 'reviewer_node', 'planner_node', 'end']` | 93-105 |  |
| 函数 `build_workflow() -> StateGraph` | 108-192 | 构建工作流图： |
| 函数 `run_analysis(question, user_id, *, company_id, conversation_context, planner_memory, attachment_context, document_ids, business_data_source, schema_catalog, semantic_review_enabled, stage_callback, checkpoint_callback, resume_next_node, resume_state, tool_runtime) -> dict` | 199-293 | 运行一次完整分析 |

## `backend/app/modules/workflow/orchestration/node_outcome.py`（24 行）

模块说明：Stable machine-readable result contract for every workflow node.

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `NodeOutcome`(BaseModel) | 19-24 |  |

## `backend/app/modules/workflow/orchestration/nodes.py`（1079 行）

模块说明：LangGraph 工作流节点 —— 每个节点封装一个 Agent 调用

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_render_clarification(plan) -> str` | 75-91 | Show the specific question when there is one; missing slots are the fallback. |
| 函数 `_set_stage(state, stage, node_name) -> None` | 94-97 |  |
| 函数 `_checkpoint(state, *, completed_node, next_node, update) -> dict` | 100-148 | Persist a node's structured output after the node has completed. |
| 函数 `_next_after_plan(plan) -> str` | 151-160 |  |
| 函数 `_effective_question(state) -> str` | 163-165 | Use the Planner's standalone question without overwriting user input. |
| 类 `_Message`() | 169-174 | A snapshot message as conversations.state_update.Message. |
| 函数 `state_extract_node(state) -> dict` | 177-213 | M7: check this message's state proposals before planning. |
| 函数 `_planner_conversation_context(state) -> dict \| None` | 219-236 | The history the Planner reads; the frozen state and summary are never part of it. |
| 函数 `_planner_history_summary(state) -> list[str] \| None` | 239-244 | C9c: the summary frozen at task creation, sent only in enforce. |
| 函数 `planner_node(state) -> dict` | 247-333 | Planner 节点：分析问题，输出计划。 |
| 函数 `planner_semantic_review_node(state) -> dict` | 336-475 | Let a second model pass check the Planner decision against the snapshot. |
| 函数 `planner_terminal_node(state) -> dict` | 478-503 | Return a deterministic terminal response for non-analysis Planner actions. |
| 函数 `planning_failure_node(state) -> dict` | 506-522 | Stop safely when the Planner model call or JSON validation failed. |
| 函数 `model_tools_enabled(company_id) -> bool` | 525-533 | Off by default; the allowlist lets one company try it before anyone else. |
| 函数 `_guarded_rag_tool() -> Tool` | 536-551 |  |
| 函数 `knowledge_node(state) -> dict` | 554-654 | Knowledge 节点：检索文档证据。 |
| 函数 `data_node(state) -> dict` | 657-860 | Data 节点：执行 SQL 查询。 |
| 函数 `_flag_contradicted_memories(state, review_result) -> None` | 863-884 | Pause memories the model doubts; a failure here must not cost the report. |
| 函数 `reviewer_node(state) -> dict` | 887-979 | Reviewer 节点：检查一致性，输出最终回答。 |
| 函数 `smart_router_node(state) -> dict` | 982-1079 | Bounded policy engine: choose a node from typed execution state only. |

## `backend/app/modules/workflow/orchestration/router.py`（230 行）

模块说明：Deterministic, bounded routing policy for one analysis workflow invocation.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_outcome_from_state(state, name) -> NodeOutcome \| None` | 29-34 | Read the durable node contract, tolerating pre-contract workflow state. |
| 函数 `build_scope_fingerprint(state, plan) -> str` | 37-51 | Bind reusable artifacts to the user, company, question, plan and documents. |
| 函数 `_validation_action(review_result) -> RoutingAction \| None` | 54-67 |  |
| 函数 `choose_next_action(state) -> tuple[RoutingAction, str]` | 70-168 | Return a policy decision without asking an LLM or inspecting answer prose. |
| 函数 `build_feedback(state, action, reason) -> dict \| None` | 171-230 |  |

## `backend/app/modules/workflow/orchestration/state.py`（57 行）

模块说明：LangGraph 工作流状态定义

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `WorkflowState`(TypedDict) | 11-57 | 在所有节点间共享的状态 |

## `backend/app/modules/workflow/outbox_tasks.py`（120 行）

模块说明：Periodic publisher for durable task creation events.

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_deliver(task_ids) -> int` | 28-43 | Queue each task on its own so one broker failure cannot strand the rest. |
| 函数 `publish_pending_analysis_task_events() -> int` | 49-57 |  |
| 函数 `recover_expired_analysis_executions() -> dict[str, int]` | 63-70 | Return expired work to the queue; the next Worker owns a fresh attempt. |
| 函数 `reconcile_stranded_analysis_tasks() -> dict[str, int]` | 76-120 | Redeliver retrying tasks whose recovery delivery never reached a Worker. |

## `backend/app/modules/workflow/repository.py`（207 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_admit_task(db, *, company_id, settings) -> None` | 27-63 |  |
| 函数 `create_task(db, user_id, question, *, conversation_id, input_message_id, context_snapshot, company_id, data_source_id, schema_snapshot_id, document_ids, input_artifact_version_ids, parent_task_id, request_id) -> AnalysisTask` | 66-138 |  |
| 函数 `get_task_document_ids(db, *, task_id) -> list[int]` | 141-150 |  |
| 函数 `get_task_input_artifact_version_ids(db, *, task_id) -> list[int]` | 153-162 |  |
| 函数 `get_task_by_id(db, task_id, user_id) -> AnalysisTask \| None` | 165-173 |  |
| 函数 `get_tasks(db, user_id) -> list[AnalysisTask]` | 176-184 |  |
| 函数 `cancel_task(db, task)` | 187-207 |  |

## `backend/app/modules/workflow/schemas.py`（78 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ConversationTaskReviewOut`(BaseModel) | 20-25 |  |
| 类 `TaskCreate`(BaseModel) | 28-31 | 创建任务时客户端发送的请求体 |
| 类 `TaskOut`(BaseModel) | 34-56 | 服务端返回的任务信息 |
| 类 `ConversationTaskOut`(BaseModel) | 59-78 | Stable task view used by the chat page while polling. |

## `backend/app/modules/workflow/service.py`（61 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `create_task_service(db, user_id, question) -> AnalysisTask` | 18-27 | 创建新任务 |
| 函数 `get_task_service(db, task_id, user_id) -> AnalysisTask \| None` | 30-32 | 根据ID查询单个任务 |
| 函数 `get_tasks_service(db, user_id) -> list[AnalysisTask]` | 35-37 | 查询用户的所有任务 |
| 函数 `cancel_task_service(db, task_id, user_id)` | 40-61 |  |

## `backend/app/modules/workflow/summary_tasks.py`（143 行）

模块说明：Summarize the messages that left a conversation's context window (C9).

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `_Message`() | 43-46 |  |
| 函数 `run_summary(db, task_id, gateway) -> str` | 49-132 | Update the summary of ``task_id``'s conversation; returns what happened. |
| 函数 `summarize_conversation(task_id) -> str` | 136-143 |  |

## `backend/app/modules/workflow/tasks.py`（1004 行）

模块说明：Celery 任务入口：读取已提交任务，执行 LangGraph，并保存图的结果。

| 名字 | 行 | 说明 |
|---|---|---|
| 函数 `_frozen_allowed_chunk_ids(db, *, task_id) -> set[int] \| None` | 87-106 | Return the persisted scope; an empty scope denies every chunk. |
| 函数 `_deterministic_validation_result(review_result, report_validated) -> dict[str, object]` | 109-127 | Persist the existing deterministic gate outcomes without inferring missing checks. |
| 函数 `_evaluation_facts(workflow_result) -> dict[str, object]` | 130-173 | Persist only structured execution facts that evaluation can later read. |
| 类 `RetryableAnalysisTaskError`(Exception) | 176-177 | A dependency failed transiently and the whole analysis can be retried. |
| 函数 `_is_retryable_exception(exc) -> bool` | 189-199 |  |
| 函数 `_retry_countdown(retries, *, random) -> float` | 202-206 | Exponential backoff with jitter in [0.5x, 1.5x] so failures do not retry in lockstep. |
| 函数 `_duration_ms(db, record) -> int \| None` | 209-216 |  |
| 函数 `_sync_assistant_message(db, record, *, status, content) -> None` | 219-234 |  |
| 函数 `_record_question_facts(db, record, execution) -> None` | 237-255 | Shadow only (B2c): observe the question; a failure here must not fail the task. |
| 函数 `_record_plan_rules(db, record, execution, plan) -> None` | 258-279 | Shadow only (B2d): what the rules would suggest beside the Planner's plan. |
| 函数 `_stop_if_cancelled(db, record) -> bool` | 282-307 | 在每次不可逆操作前，以 Worker 自己的 Session 重新确认取消状态。 |
| 函数 `_update_stage(db, record, execution, stage, node_name) -> None` | 310-336 | Persist a frontend-visible workflow stage before entering that node. |
| 函数 `_checkpoint_workflow_node(db, record, execution, completed_node, next_node, state_patch) -> None` | 352-382 | Store only JSON-safe node output while the claimed execution owns it. |
| 函数 `_claim_task(db, *, task_id, celery_task_id, worker_id) -> ClaimedExecution \| None` | 385-393 |  |
| 函数 `_maintain_execution_lease(execution)` | 397-432 | Keep a blocking workflow alive without sharing its SQLAlchemy Session. |
| 函数 `_save_conversation_state(db, record, conversation_state) -> None` | 435-458 | M7: the state this task planned with, committed with its publication. |
| 函数 `_queue_summary(record) -> None` | 461-477 | C9: summarize once the publish is committed. |
| 函数 `_save_workflow_result(db, record, execution, workflow_result) -> None` | 480-598 | 将 LangGraph 的最终 State 转为当前 AnalysisTask 的可查询结果。 |
| 函数 `_publish_approved_draft(db, record, execution) -> None` | 601-640 | Publish a pre-validated draft only after a separately audited approval. |
| 函数 `_queue_seconds(record) -> float \| None` | 643-647 |  |
| 函数 `process_analysis_task(task_id)` | 651-1004 | 用独立数据库 Session 执行一次 LangGraph 分析工作流。 |

## `backend/app/utils/document_chunk.py`（303 行）

| 名字 | 行 | 说明 |
|---|---|---|
| 类 `ChunkText`() | 14-19 | Extracted text plus the original paragraph range (one-based). |
| 函数 `chunk_text_with_metadata(content, max_tokens) -> list[ChunkText]` | 22-74 | Split text while retaining its one-based paragraph range. |
| 函数 `chunk_text(content, max_tokens) -> list[str]` | 77-82 | 将文本分块，每块不超过 max_tokens 个词。 |
| 函数 `chunk_text_with_sliding_window(content, *, max_chars, overlap_chars) -> list[ChunkText]` | 85-147 | Split text into overlapping character windows while preserving paragraph bounds. |
| 函数 `_title_sections(paragraphs) -> list[list[tuple[int, str]]]` | 160-178 | Group numbered paragraphs under their top-level title. |
| 函数 `_section_context(section) -> tuple[str, str]` | 181-191 |  |
| 函数 `_split_line(line, max_chars) -> list[str]` | 194-205 | Keep a line whole when it fits; otherwise cut at sentence ends, then by length. |
| 函数 `_body_units(lines, max_chars) -> tuple[list[str], str]` | 208-216 | The units to pack, and the header a table's pieces must each repeat. |
| 函数 `_section_passages(section, max_chars) -> list[ChunkText]` | 219-262 |  |
| 函数 `chunk_text_with_passages(content, *, max_chars) -> list[ChunkText]` | 265-282 | Split text into short passages that each say which document they came from. |
| 函数 `chunk_text_for_strategy(content, strategy) -> list[ChunkText]` | 285-293 | Return a deterministic, named chunk representation for one strategy. |
| 函数 `chunk_file(file_path, *, include_metadata) -> list[str] \| list[ChunkText]` | 296-303 | 读取文件并分块。 |

