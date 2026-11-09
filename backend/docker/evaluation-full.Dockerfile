FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements/ requirements/
RUN pip install --require-hashes -r requirements/ci-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

COPY . .
