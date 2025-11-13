import logging
from typing import List, Dict
from .config import settings

def sanitize_name(name: str) -> str:
    import re
    s = name.strip()
    s = re.sub(r"[^\w\-.]+", "_", s)
    return s

def discover_mdns(timeout: float = 4.0) -> List[Dict]:
    """
    Discover IPP/IPPS printers via mDNS (DNS-SD).
    Note: In host CUPS mode, mDNS results may not have matching queues in CUPS yet.
    """
    from zeroconf import Zeroconf, ServiceBrowser
    import threading, time

    services = ["_ipp._tcp.local.", "_ipps._tcp.local."]  # Avoid _printer._tcp (often LPD on 515)
    results = []
    lock = threading.Lock()

    class Listener:
        def remove_service(self, zc, type_, name):
            pass
        def add_service(self, zc, type_, name):
            try:
                info = zc.get_service_info(type_, name)
                if not info:
                    return
                props = {}
                for k, v in (info.properties or {}).items():
                    try:
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        props[key] = val
                    except Exception:
                        continue

                host = None
                try:
                    addrs = []
                    if hasattr(info, "parsed_scoped_addresses"):
                        addrs = info.parsed_scoped_addresses()
                    elif hasattr(info, "addresses"):
                        raw_addrs = getattr(info, "addresses", [])
                        addrs = [".".join(map(str, a)) if isinstance(a, (bytes, bytearray)) else str(a) for a in raw_addrs]
                    if addrs:
                        host = addrs[0]
                except Exception:
                    pass
                if not host:
                    server = (info.server or "").rstrip(".")
                    host = server or "localhost"
                port = info.port or 631

                rp = props.get("rp", "/ipp/print")
                if not rp.startswith("/"):
                    rp = "/" + rp
                scheme = "ipps" if type_.startswith("_ipps") else "ipp"
                uri = f"{scheme}://{host}:{port}{rp}"

                candidate = {
                    "name": sanitize_name(name.split(".")[0]),
                    "uri": uri,
                    "source": "mdns",
                    "properties": props
                }
                with lock:
                    if not any(r["name"] == candidate["name"] for r in results):
                        results.append(candidate)
            except Exception as e:
                logging.debug("mDNS add_service error: %s", e)

        def update_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        listener = Listener()
        _browsers = [ServiceBrowser(zc, s, listener) for s in services]
        time.sleep(timeout)
    finally:
        zc.close()
    return results

def discover_cups() -> List[Dict]:
    """
    Discover printers from the connected CUPS server (host or remote).
    """
    try:
        import cups
    except ImportError:
        logging.warning("pycups not available; cannot discover CUPS printers.")
        return []
    try:
        # Respect CUPS_SERVER env for socket or host:port
        import os
        if settings.cups_server and settings.cups_server.startswith("/"):
            os.environ["CUPS_SERVER"] = settings.cups_server
            conn = cups.Connection()
        elif settings.cups_server and ":" in settings.cups_server:
            host, port_str = settings.cups_server.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 631
            conn = cups.Connection(host=host, port=port)
        else:
            conn = cups.Connection()

        printers = conn.getPrinters()
        results = []
        for pname, pdata in printers.items():
            uri = pdata.get("device-uri") or pdata.get("printer-uri-supported") or ""
            results.append({
                "name": sanitize_name(pname),
                "uri": uri,
                "source": "cups"
            })
        return results
    except Exception as e:
        logging.warning("CUPS discovery failed: %s", e)
        return []

def discover_static() -> List[Dict]:
    out = []
    for sp in settings.static_printers:
        out.append({
            "name": sanitize_name(sp.name),
            "uri": getattr(sp, "uri", ""),
            "source": "static"
        })
    return out

def filter_printers(printers: List[Dict]) -> List[Dict]:
    filtered = []
    for p in printers:
        name = p["name"]
        if settings.include_regex and not settings.include_regex.search(name):
            continue
        if settings.exclude_regex and settings.exclude_regex.search(name):
            continue
        filtered.append(p)
    return filtered

def discover_all() -> List[Dict]:
    aggregated: List[Dict] = []
    for method in settings.discovery_methods:
        m = method.lower()
        try:
            if m == "cups":
                aggregated.extend(discover_cups())
            elif m == "mdns":
                aggregated.extend(discover_mdns())
            elif m == "static":
                aggregated.extend(discover_static())
            else:
                logging.warning("Unknown discovery method '%s' ignored.", m)
        except Exception as e:
            logging.warning("Discovery method %s failed: %s", m, e)

    # Deduplicate by name, preferring earlier methods (CUPS over mDNS over static)
    dedup = {}
    for p in aggregated:
        if p["name"] not in dedup:
            dedup[p["name"]] = p
    final = filter_printers(list(dedup.values()))
    return final