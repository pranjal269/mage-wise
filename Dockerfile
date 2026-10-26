# Hosted Magewise MCP server (streamable HTTP at /mcp).
#   docker build -t magewise .
#   docker run -p 8000:8000 -v magewise-data:/data \
#     -e MAGEWISE_TOKEN=... -e GITHUB_TOKEN=... -e NVIDIA_API_KEY=... magewise
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY magewise ./magewise
RUN pip install --no-cache-dir .

# Index and embedding model live on a volume so restarts don't re-index.
ENV CHROMA_PERSIST_DIR=/data/chroma HOME=/data
EXPOSE 8000
CMD ["magewise-mcp", "--http", "--host", "0.0.0.0", "--port", "8000"]
