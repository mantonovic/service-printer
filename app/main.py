import logging
import os
import signal
import json
from typing import List, Dict
from .config import settings
from .discover import discover_all, sanitize_name
from .print_service import PrintService
from .printer_monitor import PrinterMonitor

shutdown_flag = False

def handle_sigterm(signum, frame):
    global shutdown_flag
    shutdown_flag = True

def _generate_static_json_suggestion(printers: List[Dict]) -> str:
    """
    Build a PRINTER_STATIC_JSON suggestion from CUPS printers only.
    If none, return empty string.
    """
    cups_only = [p for p in printers if p.get("source") == "cups"]
    if not cups_only:
        return ""
    # Only include name for host CUPS mode (URI is optional/informational)
    suggestion = [{"name": p["name"]} for p in cups_only]
    return json.dumps(suggestion, indent=2, sort_keys=False)

def _apply_static_selection(discovered: List[Dict]) -> List[Dict]:
    """
    If PRINTER_STATIC_JSON provided, select only those queues by name.
    Prefer CUPS entries; if missing, still add a placeholder and warn.
    """
    if not settings.static_printers:
        # No static selection: default to CUPS-only to avoid mdns-only folders
        cups_only = [p for p in discovered if p.get("source") == "cups"]
        if not cups_only:
            logging.warning("No CUPS queues discovered. Ensure host CUPS is accessible.")
        return cups_only

    desired = {sp.name for sp in settings.static_printers}
    by_name = {p["name"]: p for p in discovered}
    managed: List[Dict] = []
    for name in desired:
        p = by_name.get(name)
        if p:
            managed.append(p)
        else:
            logging.warning("Static queue '%s' not found in discovery. Will create folder but printing will fail until the queue exists in CUPS.", name)
            managed.append({"name": name, "uri": "", "source": "static-only"})
    return managed

def main():
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logging.info("Starting printer discovery (methods=%s)", settings.discovery_methods)
    printers = discover_all()
    logging.info("Discovered %d printers (pre-filter)", len(printers))
    for p in printers:
        logging.info("Discovered: name=%s uri=%s source=%s", p['name'], p.get('uri'), p.get('source'))

    # If PRINTER_STATIC_JSON not set, print a suggestion built from CUPS queues
    if not settings.static_json_raw:
        suggestion = _generate_static_json_suggestion(printers)
        if suggestion:
            logging.info("PRINTER_STATIC_JSON suggestion (copy and set this env var to manage these queues explicitly):\n%s", suggestion)
        else:
            logging.info("No CUPS queues found to build PRINTER_STATIC_JSON suggestion. Ensure CUPS is accessible and queues are set up on the host.")

    # Apply static selection (if provided), else default to CUPS-only
    managed = _apply_static_selection(printers)
    logging.info("Managing %d printers", len(managed))
    for p in managed:
        logging.info("Managing: name=%s uri=%s source=%s", p['name'], p.get('uri'), p.get('source'))

    print_service = PrintService()
    monitor = PrinterMonitor(print_service.print_pdf)

    for p in managed:
        monitor.add_printer(p)

    # Allow users to create new folders; prints will only succeed if a matching CUPS queue exists
    if settings.create_missing:
        ensure_dynamic(monitor)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    logging.info("Service running (host CUPS mode). Drop PDF files into printer folders to print.")
    try:
        while not shutdown_flag:
            signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        logging.info("Shutting down.")

def ensure_dynamic(monitor: PrinterMonitor):
    import threading, time
    known = set(os.listdir(settings.base_path)) if os.path.isdir(settings.base_path) else set()

    def loop():
        while not shutdown_flag:
            try:
                os.makedirs(settings.base_path, exist_ok=True)
                current = set(os.listdir(settings.base_path))
                new_dirs = [d for d in current - known if os.path.isdir(os.path.join(settings.base_path, d))]
                for nd in new_dirs:
                    sanitized = sanitize_name(nd)
                    printer = {"name": sanitized, "uri": None, "source": "dynamic"}
                    logging.info("Registering dynamic printer folder=%s (must exist as CUPS queue to work)", nd)
                    monitor.add_printer(printer)
                    known.add(nd)
            except Exception as e:
                logging.debug("Dynamic ensure loop error: %s", e)
            time.sleep(10)
    threading.Thread(target=loop, daemon=True).start()

if __name__ == "__main__":
    main()