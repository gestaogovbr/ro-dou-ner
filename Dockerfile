FROM ghcr.io/astral-sh/uv:0.11.3 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
ARG WITH_GLINER=false
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN if [ "$WITH_GLINER" = "true" ]; then uv sync --locked --no-dev --no-editable --extra gliner; else uv sync --locked --no-dev --no-editable; fi
RUN useradd --uid 10001 --create-home ner
USER ner
EXPOSE 8000
ENTRYPOINT ["ro-dou-ner"]
CMD ["serve", "--host", "0.0.0.0"]
