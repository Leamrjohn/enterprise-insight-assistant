FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements/ requirements/
RUN pip install --require-hashes -r requirements/ci-linux-py312.lock \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements/ml-linux-py312.lock

COPY . .
