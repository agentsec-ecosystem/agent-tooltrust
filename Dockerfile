FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

RUN pip install uv && uv pip install --system . && uv pip install --system fastmcp mcp

EXPOSE 8000

CMD ["tooltrust", "serve", "--host", "0.0.0.0", "--port", "8000"]