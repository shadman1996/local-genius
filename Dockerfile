# ============================================================
# Local Genius — Dockerfile
# ============================================================
# Build:  docker build -t local-genius .
# Run:    docker run -it --network host local-genius
# ============================================================

FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash genius
USER genius
WORKDIR /home/genius/app

# Install Python dependencies
COPY --chown=genius:genius requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy source
COPY --chown=genius:genius . .

# Copy default env if not mounted
RUN cp -n .env.example .env 2>/dev/null || true

# Set PATH for user-installed packages
ENV PATH="/home/genius/.local/bin:${PATH}"

# Health check — verify Ollama is reachable
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:11434/api/tags || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--interactive"]
