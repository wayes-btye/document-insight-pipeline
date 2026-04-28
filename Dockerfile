# Document Insight Pipeline — slim runtime image.
#
# Two-stage build for layer caching: deps installed once, source copied second.
# Runs as a non-root user. No API key baked in.

FROM python:3.12-slim AS deps

WORKDIR /app

# Install only the dep manifest first so this layer caches across source changes.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      "openai>=1.40" \
      "pydantic>=2.6" \
      "httpx>=0.27" \
      "pyyaml>=6.0" \
      "tenacity>=8.2"

# ---------- runtime image ----------
FROM python:3.12-slim AS runtime

# Non-root user
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# Bring in installed deps from the deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Source
COPY src ./src
COPY eval ./eval
COPY input_docs ./input_docs
COPY config.yaml analyze_docs.py ./

RUN chown -R app:app /app
USER app

# Default: mock-mode run against the bundled corpus, no API key needed.
# Override via `docker run ... python -m src.cli --model openai/gpt-4o-mini` etc.
ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--input_dir", "input_docs", "--output", "summary_report.md", "--mock"]
