import logging
import os
import time
import subprocess
from typing import Dict
from .config import settings

class PrintService:
    def __init__(self):
        self.use_pycups = settings.use_pycups
        self._cups_conn = None
        if self.use_pycups:
            try:
                import cups  # noqa
            except ImportError:
                logging.warning("pycups not available; falling back to lp.")
                self.use_pycups = False

    def _conn(self):
        if not self.use_pycups:
            return None
        if self._cups_conn is None:
            import cups
            try:
                # Honor CUPS_SERVER for socket or host:port
                if settings.cups_server and settings.cups_server.startswith("/"):
                    os.environ["CUPS_SERVER"] = settings.cups_server
                    self._cups_conn = cups.Connection()
                elif settings.cups_server and ":" in settings.cups_server:
                    host, port_str = settings.cups_server.split(":", 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        port = 631
                    self._cups_conn = cups.Connection(host=host, port=port)
                else:
                    self._cups_conn = cups.Connection()
                if settings.cups_user:
                    self._cups_conn.setUser(settings.cups_user)
            except Exception as e:
                logging.warning("Failed to connect to CUPS server: %s", e)
                self._cups_conn = None
                self.use_pycups = False
        return self._cups_conn

    def _queue_exists(self, printer_name: str) -> bool:
        # Prefer pycups when available
        if self.use_pycups:
            try:
                conn = self._conn()
                if conn:
                    printers = conn.getPrinters()
                    return printer_name in printers
            except Exception:
                pass
        # Fallback to lpstat
        cmd = ["lpstat", "-p", printer_name]
        if settings.cups_server and not settings.cups_server.startswith("/"):
            cmd = ["lpstat", "-h", settings.cups_server, "-p", printer_name]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            return res.returncode == 0
        except Exception:
            return False

    def print_pdf(self, printer: Dict, filepath: str) -> bool:
        """
        Submit PDF to CUPS queue (by name). If queue doesn't exist in the connected CUPS, log a helpful warning.
        """
        printer_name = printer["name"]
        job_name = f"{printer_name}-{os.path.basename(filepath)}"

        for attempt in range(1, settings.print_retry_count + 1):
            try:
                # First, pycups if we can and queue exists
                if self.use_pycups:
                    conn = self._conn()
                    if conn:
                        try:
                            if self._queue_exists(printer_name):
                                job_id = conn.printFile(printer_name, filepath, job_name, {})
                                logging.info("Submitted via pycups: printer=%s job_id=%s file=%s", printer_name, job_id, filepath)
                                return True
                            else:
                                logging.warning("Queue '%s' not found in connected CUPS. Add this printer to your host CUPS, then retry.", printer_name)
                        except Exception as e:
                            logging.debug("pycups submission failed for %s: %s (will try lp)", printer_name, e)

                # Fallback to lp
                if not self._queue_exists(printer_name):
                    raise RuntimeError(f"CUPS queue '{printer_name}' not found. Ensure the queue exists on the host CUPS and the socket/server is accessible.")

                cmd = ["lp"]
                if settings.cups_server and not settings.cups_server.startswith("/"):
                    cmd += ["-h", settings.cups_server]
                cmd += ["-d", printer_name, filepath]
                logging.debug("Running command: %s", " ".join(cmd))
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                if res.returncode == 0:
                    logging.info("Print submitted via lp: printer=%s file=%s output=%s", printer_name, filepath, res.stdout.strip())
                    return True
                else:
                    raise RuntimeError(f"lp failed: {res.stderr.strip()}")

            except Exception as e:
                logging.warning("Print attempt %d/%d failed for %s: %s", attempt, settings.print_retry_count, filepath, e)
                if attempt < settings.print_retry_count:
                    time.sleep(settings.print_retry_delay)
        return False