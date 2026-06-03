# Network Printer Drop-Print (Host CUPS Mode)

## Quick start

```bash
version=$(cat ${PWD}/VERSION)
docker build -t mantonovic/printer-drop-service:$version .

mkdir -p ${PWD}/printdrop

# Grant container access to the host CUPS socket's group
CUPS_GID=$(stat -c %g /run/cups/cups.sock)

docker run --rm \
  --name printer-service \
  --network=host \
  --user $(id -u):$(id -g) \
  --group-add ${CUPS_GID} \
  -e DISCOVERY_METHODS=cups,mdns \
  -e CUPS_SERVER=/run/cups/cups.sock \
  -v /run/cups/cups.sock:/run/cups/cups.sock \
  -v /etc/cups:/etc/cups:ro \
  -v ${PWD}/printdrop:/data/printers \
  mantonovic/printer-drop-service:$version
```

Drop PDFs into `/srv/printdrop/<queue_name>/`. Each file is submitted to CUPS and then moved into `/srv/printdrop/<queue_name>/archive/`.

## Push to registry

```bash
version=$(cat ${PWD}/VERSION)
docker build -t mantonovic/printer-drop-service:$version .
docker tag mantonovic/printer-drop-service:$version mantonovic/printer-drop-service:latest
docker push mantonovic/printer-drop-service:$version
docker push mantonovic/printer-drop-service:latest
```

## PRINTER_STATIC_JSON

- If set, it explicitly controls which queues the container manages. Only those listed will get folders and be monitored. Format:

```json
[
  { "name": "QueueA" },
  { "name": "HP_Color_LaserJet_M455_B94849" }
]
```

- If not set, at startup the container will:
  - Discover available queues from CUPS,
  - Manage those queues,
  - Print a ready-to-copy PRINTER_STATIC_JSON suggestion to the logs so you can pin the set of managed queues and restart with it.

This makes it easy to lock down exactly which printers are used.

## Environment variables

- BASE_PATH=/data/printers
- ARCHIVE_SUBDIR=archive
- DISCOVERY_METHODS=cups,mdns (comma list: cups, mdns, static)
- FILE_STABLE_SECONDS=2
- PRINT_RETRY_COUNT=3
- PRINT_RETRY_DELAY=5
- INCLUDE_REGEX=
- EXCLUDE_REGEX=
- PRINTER_STATIC_JSON=
- LOG_LEVEL=INFO
- USE_PYCUPS=1
- CREATE_MISSING=1
- CUPS_SERVER=
  - Set to `/run/cups/cups.sock` to use the mounted host socket.
  - Or `host:port` to target remote CUPS directly.

## Notes

- Managing only CUPS queues by default avoids mDNS-only devices that are not set up as queues (which would fail). You can still keep mdns in discovery to aid future queue setup.
- If you see “printer or class does not exist,” ensure:
  - You mounted the socket and added its group to the container (see quick start).
  - The queue exists in host CUPS (`lpstat -p` on host).
  - CUPS_SERVER is correct.

## Troubleshooting

- Permission denied on /data/printers: run with `--user $(id -u):$(id -g)` or chown/chmod the host directory for write access.
- No queues discovered: verify CUPS is running; socket is mounted; container has the socket’s group; and `CUPS_SERVER=/run/cups/cups.sock` is set.
- Jobs fail for statically listed queues: ensure the queue name exactly matches CUPS (`lpstat -p`), and that the container can reach CUPS.
