FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# optional: fdo-consume for the FDO sources, e.g. https://github.com/FAIR2Adapt/fdo-consume/archive/v1.1.0.tar.gz (no git in the image)
ARG FDO_CONSUME_PIP=""
RUN if [ -n "$FDO_CONSUME_PIP" ]; then pip install --no-cache-dir "$FDO_CONSUME_PIP"; fi

COPY server.py README.md ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY config/ ./config/
COPY scripts/ ./scripts/

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/sources' % os.environ.get('APP_PORT','8000'))" || exit 1

CMD ["python", "server.py"]
