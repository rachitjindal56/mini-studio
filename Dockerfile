# ---- Base image for dependencies ----
    FROM ghcr.io/astral-sh/uv:0.2.12 as uv
    FROM python:3.12-slim AS builder

    WORKDIR /app
    
    COPY requirements.txt .
    RUN --mount=type=cache,target=/root/.cache/uv \
        --mount=/mnt/dfs \
        --mount=from=uv,source=/uv,target=./uv \
        ./uv pip install --system --no-cache-dir --prefix=/install -r requirements.txt
    
    FROM python:3.12-slim
    
    WORKDIR /app
    
    COPY --from=builder /install /usr/local
    
    COPY . .
    COPY .env .
    EXPOSE 8005

    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
    
