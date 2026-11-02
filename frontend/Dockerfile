
# ==========================================
# STAGE 1: BUILD FRONTEND AND PYTHON ENVIRONMENT
# ==========================================
FROM python:3.12-slim-bookworm AS builder

ARG PORT=10000
ARG API_URL

ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

# Install UV
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Create virtual environment
RUN uv venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Copy application files
COPY . .

# Install Python dependencies
RUN uv pip install --no-cache -r requirements.txt

# Initialize Reflex
RUN reflex init

# Export frontend
RUN API_URL=${API_URL:-http://localhost:${PORT}} \
    reflex export --frontend-only --no-zip && \
    mkdir -p /srv && \
    cp -r .web/_static/. /srv/ && \
    rm -rf .web


# ==========================================
# STAGE 2: PRODUCTION IMAGE
# ==========================================
FROM python:3.12-slim-bookworm AS production

ARG PORT=10000

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=${PORT}

# Install dependencies and Caddy repository
RUN apt-get update -o Acquire::Retries=3 && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https && \
    curl -1sLf \
    'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
    gpg --dearmor \
    -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf \
    'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    -o /etc/apt/sources.list.d/caddy-stable.list && \
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    chmod o+r /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get update -o Acquire::Retries=3 && \
    apt-get install -y --no-install-recommends caddy && \
    rm -rf /var/lib/apt/lists/*

# Copy Python virtual environment
COPY --from=builder /app/.venv /app/.venv

# Copy application
WORKDIR /app
COPY --from=builder /app /app

# Copy exported frontend
COPY --from=builder /srv /srv

ENV PATH="/app/.venv/bin:$PATH"

# Configure Caddy
RUN printf ':{$PORT}\n\
\n\
encode gzip\n\
\n\
@backend_routes path /_event/* /ping /_upload /_upload/*\n\
handle @backend_routes {\n\
    reverse_proxy 127.0.0.1:8000\n\
}\n\
\n\
root * /srv\n\
route {\n\
    try_files {path} {path}/ /404.html\n\
    file_server\n\
}\n' > /etc/caddy/Caddyfile

# Expose Render port
EXPOSE 10000

# Start Caddy and Reflex backend
CMD ["sh", "-c", "caddy run --config /etc/caddy/Caddyfile & reflex run --env prod --backend-only --loglevel debug"]
