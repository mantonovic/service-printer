import logging
import os
import time
import threading
import shutil
from typing import Dict, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .config import settings

class PDFHandler(FileSystemEventHandler):
    def __init__(self, printer: Dict, print_callback: Callable[[Dict, str], bool]):
        self.printer = printer
        self.print_callback = print_callback

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(".pdf"):
            return
        threading.Thread(target=self.process_file, args=(event.src_path,), daemon=True).start()

    def process_file(self, filepath: str):
        logging.info("Detected new PDF for printer %s: %s", self.printer["name"], filepath)
        if not wait_file_stable(filepath, settings.file_stable_seconds):
            logging.warning("File never stabilized (timeout) %s", filepath)
            return
        success = self.print_callback(self.printer, filepath)
        archive_dir = os.path.join(os.path.dirname(filepath), settings.archive_subdir)
        os.makedirs(archive_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        base = os.path.basename(filepath)
        new_name = f"{os.path.splitext(base)[0]}_{ts}.pdf"
        dest = os.path.join(archive_dir, new_name if success else f"FAILED_{new_name}")
        try:
            shutil.move(filepath, dest)
        except Exception as e:
            logging.error("Failed moving file to archive: %s", e)
        if success:
            logging.info("Archived printed file to %s", dest)
        else:
            logging.error("Printing failed for %s; archived as %s", filepath, dest)

def wait_file_stable(path: str, stable_seconds: int, max_wait: int = 300) -> bool:
    start = time.time()
    last_size = -1
    stable_start = None
    while True:
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            return False
        if size == last_size:
            if stable_start is None:
                stable_start = time.time()
            elif time.time() - stable_start >= stable_seconds:
                return True
        else:
            stable_start = None
            last_size = size
        if time.time() - start > max_wait:
            return False
        time.sleep(0.5)

class PrinterMonitor:
    def __init__(self, print_callback):
        self.print_callback = print_callback
        self.observers = []

    def add_printer(self, printer: Dict):
        path = os.path.join(settings.base_path, printer["name"])
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, settings.archive_subdir), exist_ok=True)
        handler = PDFHandler(printer, self.print_callback)
        obs = Observer()
        obs.schedule(handler, path, recursive=False)
        obs.start()
        self.observers.append(obs)
        logging.info("Monitoring printer folder: %s (uri=%s source=%s)", path, printer.get("uri"), printer.get("source"))

    def stop(self):
        for o in self.observers:
            o.stop()
        for o in self.observers:
            o.join()