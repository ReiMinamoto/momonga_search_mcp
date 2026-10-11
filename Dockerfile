FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir uv==0.12.23 && uv sync --locked --no-dev \
    && useradd --uid 10001 --create-home mcp \
    && mkdir -p /var/cache/momonga /run/momonga-tokens \
    && chown mcp:mcp /var/cache/momonga /run/momonga-tokens
USER mcp
ENV MOMONGA_SEARCH_MCP_CACHE_DIR=/var/cache/momonga
ENV PATH="/app/.venv/bin:${PATH}"
ENTRYPOINT ["momonga-search-mcp"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
