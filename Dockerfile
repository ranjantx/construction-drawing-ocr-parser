# syntax=docker/dockerfile:1.7
# AECInspire Parser API — lightweight CPU image
# Build:  docker build -t aecinspire/parser-api:latest .
# Run:    docker run -p 8001:8001 aecinspire/parser-api:latest

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System libs: OpenCV headless needs libglib, PyMuPDF needs libmupdf deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install requirements
COPY requirements_api.txt .
RUN pip install -r requirements_api.txt

# Pre-cache EasyOCR model weights (~120 MB) — avoids cold-start download
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False); print('EasyOCR models cached')"

# Copy source
COPY . .

# Create output directory
RUN mkdir -p /app/output/api

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]


# ── GPU training target (for YOLO fine-tuning on EC2 g4dn) ──────────────────
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS gpu-trainer

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip \
    libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install ultralytics pyyaml

COPY . .
ENTRYPOINT ["python", "-m", "electrical.train_yolo"]
