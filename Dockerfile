FROM python:3.12-slim

# System packages: CUPS client/tools, dev headers for pycups, and mDNS helpers
RUN apt-get update && apt-get install -y --no-install-recommends \
    cups-client libcups2-dev gcc avahi-daemon libnss-mdns ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m appuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV BASE_PATH=/data/printers \
    ARCHIVE_SUBDIR=archive \
    DISCOVERY_METHODS=cups,mdns \
    FILE_STABLE_SECONDS=2 \
    PRINT_RETRY_COUNT=3 \
    PRINT_RETRY_DELAY=5 \
    LOG_LEVEL=INFO \
    USE_PYCUPS=1 \
    CREATE_MISSING=1 \
    CUPS_SERVER= \
    PRINTER_STATIC_JSON=

VOLUME ["/data/printers"]
USER appuser
ENTRYPOINT ["/entrypoint.sh"]