FROM python:3.12-slim

# System deps: ffmpeg, chromium for selenium, fonts for subtitles
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    chromium \
    chromium-driver \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Playwright chromium (for tiktok-uploader)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN pip install --no-cache-dir playwright && playwright install chromium --with-deps

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create storage dirs
RUN mkdir -p storage/cookies storage/output/terror storage/output/historias storage/output/dinero \
    music/royalty_free/terror music/royalty_free/historias music/royalty_free/dinero

# Expose dashboard
EXPOSE 8000

# Healthcheck — uses public /health endpoint (no auth required)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health >/dev/null || exit 1

# Use tini as PID 1 for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]
