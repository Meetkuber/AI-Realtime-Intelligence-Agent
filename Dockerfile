# ─────────────────────────────────────────────────────────────
# Stage 1: Frontend build
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────
# Stage 2: Backend runtime
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS backend

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY backend/ ./backend/
COPY evals/ ./evals/

# Frontend dist (served as static files by FastAPI if needed)
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Non-root user
RUN useradd -m -u 1001 aria
USER aria

# SQLite DB will be created at runtime in /app/aria.db
VOLUME ["/app"]

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
