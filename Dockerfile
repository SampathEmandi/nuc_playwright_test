# Start from a lightweight Python base image
FROM python:3.12-slim

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    TZ=UTC \
    DEBIAN_FRONTEND=noninteractive \
    NODE_OPTIONS=--max-old-space-size=4096

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies required by Playwright and Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdbus-1-3 \
    libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libxss1 libgtk-3-0 libx11-xcb1 fonts-liberation xdg-utils \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
    libglib2.0-0 libxshmfence1 libxkbcommon0 libxrender1 libxtst6 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install pandoc and LaTeX dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install git (required for some dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using uv with lock file (frozen = no updates)
# --no-dev = skip development dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Install Playwright browsers (including Chromium)
# Set NODE_TLS_REJECT_UNAUTHORIZED=0 to handle self-signed certificates in corporate/proxy environments
# This is only set during build time, not in runtime
# Use uv run to execute playwright in the virtual environment created by uv
RUN NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install --with-deps chromium

# Set the working directory
WORKDIR /app

# Copy your app code into the container
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app with reload
# Use uv run to execute uvicorn in the virtual environment
CMD uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload

