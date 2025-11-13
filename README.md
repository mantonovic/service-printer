# Network Printer Drop-Print (Host CUPS Mode)

This container reuses your host CUPS daemon. It discovers printers (CUPS queues), creates a folder per queue, and prints any PDF dropped into those folders to the corresponding queue. Files are archived after submission.

## Why host CUPS?

- Your host already has queues configured (IPP, LPD, JetDirect, authentication, etc.).
- Inside the container, we connect directly to your host CUPS, so queue names and behavior are identical.

## Using the Published Image

The image is published at:

`registry.gitlab.com/tdmsa/service-printer:1.0.0`

You do NOT need to build locally unless you are developing changes. Pulling and running is enough.

### 1. Prerequisites

- A host running CUPS with queues already configured (check with `lpstat -p`).
- The CUPS UNIX domain socket location (usually `/run/cups/cups.sock` or `/var/run/cups/cups.sock`).
- A writable directory on the host for dropped PDFs and archives (e.g. `${PWD}/printdrop`).
- (Recommended) Run the container with your user UID/GID and add the CUPS socket’s group so the socket can be accessed.

Find the socket group GID:

```bash
stat -c %g /run/cups/cups.sock
```

### 2. Simple One‑Shot Run

If you just want to test quickly (assumes socket at `/run/cups/cups.sock`):

```bash
mkdir -p ${PWD}/printdrop
CUPS_GID=$(stat -c %g /run/cups/cups.sock)

docker run --rm \
  --name service-printer \
  --network=host \
  --user $(id -u):$(id -g) \
  --group-add ${CUPS_GID} \
  -e CUPS_SERVER=/run/cups/cups.sock \
  -e DISCOVERY_METHODS=cups,mdns \
  -v /run/cups/cups.sock:/run/cups/cups.sock \
  -v /etc/cups:/etc/cups:ro \
  -v ${PWD}/printdrop:/data/printers \
  registry.gitlab.com/tdmsa/service-printer:1.0.0
```

Then drop a PDF file:

```bash
cp invoice123.pdf ${PWD}/printdrop/<queue_name>/
```

After submission the file is moved to:

```
${PWD}/printdrop/<queue_name>/archive/invoice123_YYYYmmdd-HHMMSS.pdf
```

### 3. Locking Down Managed Queues (PRINTER_STATIC_JSON)

First run without `PRINTER_STATIC_JSON`. The container will log a suggestion:

```
PRINTER_STATIC_JSON suggestion (copy and set this env var ...):
[
  { "name": "HP_Color_LaserJet_M455_B94849" },
  { "name": "Brother_DCP_L3550CDW_series" }
]
```

Copy that JSON and pass on next run:

```bash
-e PRINTER_STATIC_JSON='[{"name":"HP_Color_LaserJet_M455_B94849"},{"name":"Brother_DCP_L3550CDW_series"}]'
```

Only those folders will be created and monitored.

You can also use the short form list of strings:

```bash
-e PRINTER_STATIC_JSON='["HP_Color_LaserJet_M455_B94849","Brother_DCP_L3550CDW_series"]'
```

### 4. Environment Variables Summary

| Variable | Meaning | Typical Value |
|----------|---------|---------------|
| CUPS_SERVER | Path to socket or host:port of CUPS | /run/cups/cups.sock |
| DISCOVERY_METHODS | Comma list: cups, mdns, static | cups,mdns |
| PRINTER_STATIC_JSON | Explicit printers to manage (queue names) | JSON array |
| BASE_PATH | Root folder for printer directories | /data/printers |
| ARCHIVE_SUBDIR | Archive subfolder name | archive |
| FILE_STABLE_SECONDS | Seconds file size must remain unchanged | 2 |
| PRINT_RETRY_COUNT | Attempts per file | 3 |
| PRINT_RETRY_DELAY | Seconds between retries | 5 |
| LOG_LEVEL | Logging level | INFO |
| USE_PYCUPS | Use pycups if available (1/0) | 1 |
| CREATE_MISSING | Monitor base path for new folders | 1 |
| INCLUDE_REGEX | Only manage names matching regex | (optional) |
| EXCLUDE_REGEX | Exclude names matching regex | (optional) |

### 5. Docker Compose Usage

Create `docker-compose.yml` (Compose v3+). Adjust socket path if different.

```yaml
services:
  service-printer:
    image: registry.gitlab.com/tdmsa/service-printer:1.0.0
    container_name: service-printer
    network_mode: host            # For CUPS socket + optional mDNS visibility
    user: "${UID}:${GID}"         # Export your UID/GID before running: export UID=$(id -u); export GID=$(id -g)
    group_add:
      - "${CUPS_GID}"             # export CUPS_GID=$(stat -c %g /run/cups/cups.sock)
    environment:
      CUPS_SERVER: /run/cups/cups.sock
      DISCOVERY_METHODS: cups,mdns
      LOG_LEVEL: INFO
      PRINT_RETRY_COUNT: 3
      PRINT_RETRY_DELAY: 5
      FILE_STABLE_SECONDS: 2
      # Uncomment to lock printers:
      # PRINTER_STATIC_JSON: '[{"name":"HP_Color_LaserJet_M455_B94849"},{"name":"Brother_DCP_L3550CDW_series"}]'
    volumes:
      - /run/cups/cups.sock:/run/cups/cups.sock
      - /etc/cups:/etc/cups:ro
      - ${PWD}/printdrop:/data/printers
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "bash", "-c", "test -S /run/cups/cups.sock && ls /data/printers || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

Bring it up:

```bash
export UID=$(id -u)
export GID=$(id -g)
export CUPS_GID=$(stat -c %g /run/cups/cups.sock)
mkdir -p ${PWD}/printdrop
docker compose up -d
```

View logs:

```bash
docker compose logs -f service-printer
```

### 6. Updating the Image

To pull a newer patch release:

```bash
docker pull registry.gitlab.com/tdmsa/service-printer:1.0.1
docker compose up -d --force-recreate
```

(Adjust tag as new versions are published.)

### 7. Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Queue folder exists but print fails with “not found” | Queue not defined in host CUPS | Add queue in CUPS (`lpadmin` or UI), restart container |
| Permission denied on socket | Missing group-add for socket’s group GID | Add `group_add: [ "${CUPS_GID}" ]` |
| No suggestion JSON printed | No CUPS queues discovered | Check CUPS is running; verify socket path & permissions |
| mDNS printers show but fail to print | Device discovered, queue not added to CUPS | Add queue to CUPS; then restart |

### 8. Archiving Behavior

Printed PDF → renamed with timestamp:
```
original.pdf -> original_20251113-134500.pdf
```
Failed print → prefixed with `FAILED_`:
```
FAILED_original_20251113-134500.pdf
```

### 9. Locking Down Access

If you want to prevent ad‑hoc folder creation:
- Set `CREATE_MISSING=0`
- Provide `PRINTER_STATIC_JSON` with the exact queues.

### 10. Uninstall / Cleanup

```bash
docker compose down
rm -rf ${PWD}/printdrop
```

(Keep archives as needed before deletion.)

---

If you need a variant adding job status polling or multi-format conversion, open an issue or request it.