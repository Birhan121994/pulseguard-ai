FROM python:3.10.8 AS builder

ARG PORT=10000
ARG API_URL

ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

RUN mkdir -p /app/.web
RUN $HOME/.local/bin/uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY . .

RUN $HOME/.local/bin/uv pip install -r requirements.txt

RUN reflex init

RUN API_URL=${API_URL:-http://localhost:${PORT}} reflex export --frontend-only --no-zip && mv .web/_static/* /srv/ && rm -rf .web

FROM python:3.10.8-slim

ARG PORT=10000

RUN apt-get update -y && \
    apt-get install -y curl gnupg debian-keyring debian-archive-keyring apt-transport-https && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o /etc/apt/sources.list.d/caddy-stable.list && \
    chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    chmod o+r /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get update -y && \
    apt-get install -y caddy && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PORT=$PORT PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /srv /srv

# Inline Caddyfile
RUN cat > /etc/caddy/Caddyfile <<EOF
:{\$PORT}

encode gzip

@backend_routes path /_event/* /ping /_upload /_upload/*
handle @backend_routes {
    reverse_proxy localhost:8000
}

root * /srv
route {
    try_files {path} {path}/ /404.html
    file_server
}
EOF

STOPSIGNAL SIGKILL
EXPOSE $PORT

CMD ["sh", "-c", "caddy start --config /etc/caddy/Caddyfile && reflex run --env prod --backend-only --loglevel debug"]