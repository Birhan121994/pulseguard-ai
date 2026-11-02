# =========================
# BUILDER STAGE
# =========================
FROM python:3.12-slim-bookworm AS builder

ARG PORT=10000
ARG API_URL

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Create virtual environment
RUN uv venv /app/.venv

ENV PATH="/app/.venv/bin:/root/.local/bin:$PATH"

# Copy application
COPY . .

# Install Python dependencies
RUN uv pip install --no-cache -r requirements.txt

# Ensure pandas and SQLModel dependencies are installed
RUN uv pip install --no-cache "pandas==2.2.3" "sqlmodel==0.0.23"

# Initialize Reflex
RUN reflex init

# Build frontend
RUN API_URL=${API_URL:-http://localhost:${PORT}} \
    reflex export --frontend-only --no-zip && \
    mkdir -p /srv && \
    cp -r .web/_static/. /srv/ && \
    rm -rf .web


# =========================
# PRODUCTION STAGE
# =========================
FROM python:3.12-slim-bookworm AS production

ARG PORT=10000

ENV PORT=${PORT} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install production dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    && curl -1sLf \
    'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
    gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf \
    'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    -o /etc/apt/sources.list.d/caddy-stable.list \
    && chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && chmod o+r /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends caddy \
    && rm -rf /var/lib/apt/lists/*

# Copy application and virtual environment
WORKDIR /app

COPY --from=builder /app /app
COPY --from=builder /srv /srv

# Configure Caddy
RUN printf '{\n\
    admin off\n\
    auto_https off\n\
}\n\
:%s {\n\
    encode gzip\n\
\n\
    @backend_routes path /_event/* /ping /_upload /_upload/*\n\
\n\
    handle @backend_routes {\n\
        reverse_proxy 127.0.0.1:8000\n\
    }\n\
\n\
    handle {\n\
        root * /srv\n\
        try_files {path} {path}/ /404.html\n\
        file_server\n\
    }\n\
}\n' "$PORT" > /etc/caddy/Caddyfile

EXPOSE ${PORT}

# Start Reflex backend first, then Caddy in foreground
CMD ["sh", "-c", "reflex run --env prod --backend-only --loglevel debug & REFLEX_PID=$!; caddy run --config /etc/caddy/Caddyfile --adapter caddyfile & CADDY_PID=$!; trap 'kill $REFLEX_PID $CADDY_PID 2>/dev/null; wait' TERM INT; wait $REFLEX_PID; STATUS=$?; kill $CADDY_PID 2>/dev/null; exit $STATUS"]
