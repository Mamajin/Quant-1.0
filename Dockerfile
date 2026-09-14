# Local, free options-flow & quant-trading app (manual sec 2.9: "uv (env/deps)
# + Docker Compose (optional)"). Single image; docker-compose.yml picks which
# entrypoint (UI / API / scheduler) each container runs.
FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies before copying source so dependency changes (slow)
# are cached separately from source changes (fast) -- --no-install-project
# skips building/installing the local `quantify` package itself here.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY config/ config/
COPY src/ src/
RUN uv sync --frozen --no-dev

ENV QUANTIFY_CONFIG=/app/config/config.toml

EXPOSE 8501 8000

CMD ["uv", "run", "streamlit", "run", "src/quantify/ui/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
