# ── Stage 1: Build React/Vite frontend ───────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline

COPY frontend/ ./

# Build — vite-plugin-cesium copies Workers to dist/cesium/
RUN npm run build


# ── Stage 2: Python backend + serve static bundle ────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/ ./backend/

# Frontend static bundle from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --loop uvloop --http httptools"]
