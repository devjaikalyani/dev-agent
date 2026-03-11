FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl grep ripgrep && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Container runs offline — dependencies installed at runtime from requirements.txt
