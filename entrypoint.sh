#!/usr/bin/env bash
set -e

# Ensure base path exists and is writable
mkdir -p "${BASE_PATH:-/data/printers}" || true
if [ ! -w "${BASE_PATH:-/data/printers}" ]; then
  echo "ERROR: BASE_PATH '${BASE_PATH:-/data/printers}' not writable by $(id -u):$(id -g)."
  ls -ld "${BASE_PATH:-/data/printers}" || true
  exit 1
fi

# CUPS check and hints
if [ -n "${CUPS_SERVER}" ]; then
  if [[ "${CUPS_SERVER}" = /* ]]; then
    # Looks like a socket path
    if [ ! -S "${CUPS_SERVER}" ]; then
      echo "WARNING: CUPS_SERVER points to '${CUPS_SERVER}', but that socket does not exist."
      echo "         Mount the host socket, e.g.: -v /run/cups/cups.sock:/run/cups/cups.sock"
    fi
    echo "Using CUPS UNIX socket: ${CUPS_SERVER}"
  else
    echo "Using remote CUPS server: ${CUPS_SERVER}"
  fi
else
  if [ -S /run/cups/cups.sock ]; then
    echo "Found CUPS socket at /run/cups/cups.sock; consider setting CUPS_SERVER=/run/cups/cups.sock"
  else
    echo "WARNING: No CUPS_SERVER set and no /run/cups/cups.sock found. CUPS discovery/printing will likely fail."
  fi
fi

echo "Starting printer drop service (host CUPS mode)..."
exec python -m app.main