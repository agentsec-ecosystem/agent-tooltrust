FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

# Install the local package. --no-cache sets UV_NO_CACHE so the build always
# re-reads the copied src/ (avoids stale wheels when new modules are added).
RUN pip install uv && UV_NO_CACHE=1 uv pip install --system --no-cache . \
    && UV_NO_CACHE=1 uv pip install --system --no-cache fastmcp mcp

EXPOSE 8000

CMD ["tooltrust", "serve", "--host", "0.0.0.0", "--port", "8000"]