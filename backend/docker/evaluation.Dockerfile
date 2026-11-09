FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# C1: tokenizer files baked in, so counting tokens needs no network.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken

# The full-corpus retrieval evaluation uses the same local embedding and
# reranking providers as the Worker, so it needs CPU model-dependency parity.
# It still contains no provider-backed model dependency.  The test tools come
# from the CI lock, so this image matches the CI behavior gate.
COPY requirements/ requirements/
RUN pip install --require-hashes -r requirements/ci-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

RUN python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('o200k_base', 'cl100k_base')]"     && chmod -R a+rX /opt/tiktoken

COPY . .
