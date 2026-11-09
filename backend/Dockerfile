# backend/Dockerfile — build from the repo root: docker build -f backend/Dockerfile .
FROM python:3.12-slim

# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /srv/backend

# Dependencies first (cached layer), from the lockfile only, without dev tools.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# App code and its data inputs (resolved relative to the repo layout: /srv/backend/app -> /srv/data, /srv/ml).
COPY backend/app ./app
COPY data/templates /srv/data/templates
COPY data/names.json data/outcome_model.json /srv/data/
# Trained ranker artefacts from `make models` (gitignored; without them the API falls back to the rule, MD-09)
COPY ml/artifacts /srv/ml/artifacts
RUN uv sync --frozen --no-dev

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
