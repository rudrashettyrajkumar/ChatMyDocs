# Featherweight image — slim base, no build of native ML deps.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Single uvicorn worker — Railway Hobby is a small container. `exec` form via
# sh -c so Railway's injected $PORT is honoured (default 8000 locally) while
# uvicorn replaces the shell as PID 1's child and receives SIGTERM directly —
# a clean shutdown on Railway redeploys.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
