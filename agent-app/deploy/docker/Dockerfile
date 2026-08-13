# Builds the Agent API from the repository's two-package uv workspace.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_BACKEND=mock \
    MEDIA_OUTPUT_DIR=/workspace/agent-app/runtime

WORKDIR /workspace
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY agent-app/agent-core ./agent-app/agent-core
COPY agent-app/api ./agent-app/api
RUN uv sync --frozen --no-dev
RUN mkdir -p /workspace/agent-app/runtime

EXPOSE 8888
CMD ["uv", "run", "uvicorn", "ecommerce_api.main:app", "--host", "0.0.0.0", "--port", "8888"]
