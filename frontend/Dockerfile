
# =========================
# BUILDER STAGE
# =========================
FROM python:3.12-slim-bookworm AS builder

ARG PORT=10000
ARG API_URL

ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:/app/.venv/bin:$PATH"

# Install system dependencies required by Reflex
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        unzip \
        ca-certificates \
        build-essential \
        procps && \
    rm -rf /var/lib/apt/lists/*

# Install uv
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

WORKDIR /app

# Create virtual environment
RUN uv venv /app/.venv

# Copy application files
COPY . .

# Install Python dependencies
RUN uv pip install --python /app/.venv/bin/python -r requirements.txt

# Explicitly ensure pandas and Plotly are installed
RUN uv pip install --python /app/.venv/bin/python \
    pandas==2.2.3 \
    numpy==2.1.1 \
    plotly==5.24.1

# Verify dependencies
RUN /app/.venv/bin/python -c \
    "import pandas; import plotly.express as px; print('Pandas and Plotly installed successfully')"

# Initialize Reflex
RUN reflex init

# Export frontend
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

ENV PORT=${PORT}
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Install Caddy dependencies and unzip
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        debian-keyring \
        debian-archive-keyring \
        apt-transport-https \
        unzip && \
    curl -1sLf \
        'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor \
        -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf \
        'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        -o /etc/apt/sources.list.d/caddy-stable.list && \
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    chmod o+r /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends caddy && \
    rm -rf /var/lib/apt/lists/*

# Copy Python virtual environment
COPY --from=builder /app/.venv /app/.venv

# Copy application
WORKDIR /app
COPY --from=builder /app /app

# Copy exported frontend
COPY --from=builder /srv /srv

# Configure Caddy
RUN printf ':%s {\n\
    encode gzip\n\
    @backend_routes path /_event/* /ping /_upload /_upload/*\n\
    handle @backend_routes {\n\
        reverse_proxy 127.0.0.1:8000\n\
    }\n\
    handle {\n\
        root * /srv\n\
        try_files {path} {path}/ /404.html\n\
        file_server\n\
    }\n\
}\n' "$PORT" > /etc/caddy/Caddyfile

EXPOSE ${PORT}

STOPSIGNAL SIGTERM

# Start backend and Caddy
CMD ["sh", "-c", "reflex run --env prod --backend-only --loglevel debug & reflex_pid=$!; caddy run --config /etc/caddy/Caddyfile --adapter caddyfile & caddy_pid=$!; trap 'kill $reflex_pid $caddy_pid 2>/dev/null; wait' TERM INT; wait -n $reflex_pid $caddy_pid; exit_code=$?; kill $reflex_pid $caddy_pid 2>/dev/null; wait; exit $exit_code"]
