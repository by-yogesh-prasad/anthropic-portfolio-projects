# Official Playwright image — has Chromium + all system deps pre-installed.
# Version tag must match the playwright package in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD wget -qO- http://localhost:8000/health || exit 1

# Single worker — required because background ingest jobs live in daemon threads
# inside the process. Multi-worker (--workers N) splits into N separate processes
# that don't share the _jobs dict or thread state.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
