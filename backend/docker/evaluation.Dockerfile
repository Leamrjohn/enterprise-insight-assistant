FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# The full-corpus retrieval evaluation uses the same local embedding and
# reranking providers as the Worker, so it needs CPU model-dependency parity.
# It still contains no provider-backed model dependency.
COPY requirements/ requirements/
RUN pip install --upgrade pip \
    && pip install -r requirements/evaluation.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
    && pip install -r requirements/ml.txt

COPY . .
