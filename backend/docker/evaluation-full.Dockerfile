FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements/ requirements/
RUN pip install --upgrade pip \
    && pip install -r requirements/evaluation.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
    && pip install -r requirements/evaluation-full.txt

COPY . .
