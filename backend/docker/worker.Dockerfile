FROM python:3.12-slim

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

COPY requirements/ requirements/

RUN pip install --require-hashes -r requirements/base-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs /app/storage \
    && chown -R app:app /app

COPY --chown=app:app . .

USER app
