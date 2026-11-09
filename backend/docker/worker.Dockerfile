FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# After the apt layer, so a tokenizer change never invalidates the system
# packages (the apt mirror is the flakiest download in this build).
# C1: tokenizer files baked in, so counting tokens needs no network.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken

COPY requirements/ requirements/

RUN pip install --require-hashes -r requirements/base-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/storage /heartbeat \
    && chown -R app:app /app /heartbeat

RUN python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('o200k_base', 'cl100k_base')]"     && chmod -R a+rX /opt/tiktoken

COPY --chown=app:app . .

USER app
