# MLServer + aissemble Sumy (mirrors deploy/docker YOLO layout; separate image/port).
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY deploy/sumy/requirements.txt .

RUN uv venv .venv && \
    uv pip install --no-cache -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

COPY models/sumy /app/models/sumy

RUN echo '{"host": "0.0.0.0", "http_port": 8080, "grpc_port": 8081, "parallel_workers": 0}' > /app/models/settings.json

EXPOSE 8080 8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/v2/health/ready')" || exit 1

CMD ["mlserver", "start", "/app/models"]
