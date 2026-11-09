FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# The full-corpus retrieval evaluation uses the same local embedding and
# reranking providers as the Worker, so it needs CPU model-dependency parity.
# It still contains no provider-backed model dependency.  The test tools come
# from the CI lock, so this image matches the CI behavior gate.
COPY requirements/ requirements/
RUN pip install --require-hashes -r requirements/ci-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

COPY . .
