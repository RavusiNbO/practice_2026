FROM --platform=amd64 python:3.14-trixie
WORKDIR /app
RUN python3 -m pip install --no-cache-dir uv
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen
COPY documents/ ./documents/

COPY --exclude=documents/** --exclude=models/** . .

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["fastmcp", "run"]
CMD ["main.py:mcp", "--transport", "http", "--port", "8000", "--host", "0.0.0.0"]