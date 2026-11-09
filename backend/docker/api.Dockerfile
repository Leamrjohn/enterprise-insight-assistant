FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# C1: tokenizer files baked in, so counting tokens needs no network.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken

COPY requirements/ requirements/

RUN pip install --require-hashes -r requirements/base-linux-py312.lock

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/storage /heartbeat \
    && chown -R app:app /app /heartbeat

RUN python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('o200k_base', 'cl100k_base')]"     && chmod -R a+rX /opt/tiktoken

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
