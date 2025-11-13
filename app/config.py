import os
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern

@dataclass
class StaticPrinter:
    # In host CUPS mode, 'name' must match a CUPS queue name
    name: str
    # Optional, informational only
    uri: str = ""

@dataclass
class Settings:
    base_path: str = os.getenv("BASE_PATH", "/data/printers")
    archive_subdir: str = os.getenv("ARCHIVE_SUBDIR", "archive")
    discovery_methods: List[str] = field(default_factory=lambda: [
        m.strip() for m in os.getenv("DISCOVERY_METHODS", "cups,mdns").split(",") if m.strip()
    ])
    file_stable_seconds: int = int(os.getenv("FILE_STABLE_SECONDS", "2"))
    print_retry_count: int = int(os.getenv("PRINT_RETRY_COUNT", "3"))
    print_retry_delay: int = int(os.getenv("PRINT_RETRY_DELAY", "5"))
    include_regex_raw: str = os.getenv("INCLUDE_REGEX", "").strip()
    exclude_regex_raw: str = os.getenv("EXCLUDE_REGEX", "").strip()
    static_json_raw: str = os.getenv("PRINTER_STATIC_JSON", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    use_pycups: bool = os.getenv("USE_PYCUPS", "1") == "1"
    create_missing: bool = os.getenv("CREATE_MISSING", "1") == "1"

    # CUPS connection configuration
    cups_server: str = os.getenv("CUPS_SERVER", "").strip()  # host:port or /run/cups/cups.sock
    cups_user: str = os.getenv("CUPS_USER", "").strip()
    cups_password: str = os.getenv("CUPS_PASSWORD", "").strip()

    include_regex: Optional[Pattern] = field(init=False)
    exclude_regex: Optional[Pattern] = field(init=False)
    static_printers: List[StaticPrinter] = field(init=False)

    def __post_init__(self):
        self.include_regex = re.compile(self.include_regex_raw) if self.include_regex_raw else None
        self.exclude_regex = re.compile(self.exclude_regex_raw) if self.exclude_regex_raw else None
        if self.static_json_raw:
            try:
                data = json.loads(self.static_json_raw)
                # allow simple ["QueueA","QueueB"] too
                if isinstance(data, list) and data and isinstance(data[0], str):
                    self.static_printers = [StaticPrinter(name=item) for item in data]
                else:
                    self.static_printers = [StaticPrinter(**item) for item in data]
            except Exception:
                self.static_printers = []
        else:
            self.static_printers = []

settings = Settings()