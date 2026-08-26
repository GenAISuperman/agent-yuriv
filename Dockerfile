# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

COPY --from=builder /install /usr/local

COPY src/ /app/src/
COPY prompts/ /app/prompts/

RUN useradd -m -u 1000 appuser
USER appuser

WORKDIR /app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.agent:app", "--host", "0.0.0.0", "--port", "8000"]
