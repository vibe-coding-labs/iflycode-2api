FROM python:3.12-slim-bookworm AS backend

WORKDIR /app

# Install system dependencies for bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY iflycode_proxy/ iflycode_proxy/

RUN pip install --no-cache-dir -e .

FROM node:20-slim AS frontend-builder
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npx vite build

FROM python:3.12-slim-bookworm
WORKDIR /app

COPY --from=backend /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=backend /app/iflycode_proxy/ iflycode_proxy/
COPY --from=frontend-builder /web/../iflycode_proxy/static/ iflycode_proxy/static/

EXPOSE 40419

ENTRYPOINT ["iflycode-proxy", "serve", "-H", "0.0.0.0", "-p", "40419"]
