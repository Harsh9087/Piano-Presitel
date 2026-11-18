"""Pico W background schedule synchronizer.

Uses native MicroPython usocket for robust, dependency-free HTTP communication.
No external urequests library required!
"""
import time
import network
import _thread
import os

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import ujson as json
except ImportError:
    import json

# Configuration defaults (configured dynamically by main.py)
WIFI_SSID = "PT SOLAR"
WIFI_PASSWORD = "tcf@praful"
API_BASE = "http://66.116.251.98:8012/api"
DEVICE_API_KEY = "dev-device-key-67890"
DEVICE_ID = "pico-w-01"
POLL_SECONDS = 60

_schedule_update_pending = False
_sync_lock = _thread.allocate_lock()


def configure(api_base=None, api_key=None, device_id=None, poll_seconds=None, wifi_ssid=None, wifi_password=None):
    """Configure API and device credentials dynamically."""
    global API_BASE, DEVICE_API_KEY, DEVICE_ID, POLL_SECONDS, WIFI_SSID, WIFI_PASSWORD
    if api_base:
        API_BASE = api_base.rstrip('/')
    if api_key:
        DEVICE_API_KEY = api_key
    if device_id:
        DEVICE_ID = device_id
    if poll_seconds:
        POLL_SECONDS = poll_seconds
    if wifi_ssid:
        WIFI_SSID = wifi_ssid
    if wifi_password:
        WIFI_PASSWORD = wifi_password


def _parse_url(url):
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]
    host_port, _, path = url.partition("/")
    path = "/" + path
    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    else:
        port = 80
    return host, port, path


def _http_request(method, url, payload=None):
    """Robust, dependency-free HTTP/1.0 client using native sockets."""
    host, port, path = _parse_url(url)
    body = json.dumps(payload) if payload is not None else None

    ai = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    s = socket.socket(ai[0][0], ai[0][1], ai[0][2])
    s.settimeout(15)
    try:
        print("Sync: Connecting to {}:{}...".format(host, port))
        s.connect(ai[0][-1])

        headers = [
            "{} {} HTTP/1.0".format(method, path),
            "Host: {}:{}".format(host, port),
            "User-Agent: PicoW",
            "X-API-Key: {}".format(DEVICE_API_KEY),
            "Connection: close"
        ]
        if body is not None:
            headers.append("Content-Type: application/json")
            headers.append("Content-Length: {}".format(len(body)))

        request_data = "\r\n".join(headers) + "\r\n\r\n"
        if body is not None:
            request_data += body

        s.sendall(request_data.encode("utf-8"))

        chunks = []
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            chunks.append(chunk)

        raw = b"".join(chunks).decode("utf-8", "ignore")
        if not raw:
            raise Exception("Empty response from server")

        header_part, _, body_part = raw.partition("\r\n\r\n")
        status_line = header_part.split("\r\n")[0]
        parts = status_line.split()
        if len(parts) < 2:
            raise Exception("Malformed status line: {}".format(status_line))

        status_code = int(parts[1])
        if status_code not in (200, 201):
            raise Exception("HTTP status {}: {}".format(status_code, body_part[:80]))

        return body_part
    finally:
        s.close()


def _read_local_version():
    try:
        with open("schedule.version", "r") as f:
            return int(f.read().strip())
    except Exception:
        return -1


def _write_local_version(version):
    with open("schedule.version.tmp", "w") as f:
        f.write(str(version))
    try:
        os.remove("schedule.version")
    except OSError:
        pass
    os.rename("schedule.version.tmp", "schedule.version")


def _validate_csv(csv_text):
    lines = [line.strip() for line in csv_text.splitlines() if line.strip()]
    if not lines or lines[0].lower().replace(" ", "") != "day,starttime,sec":
        raise ValueError("CSV header is invalid")

    allowed_days = ("monday", "tuesday", "wednesday", "thursday",
                    "friday", "saturday", "sunday")
    count = 0
    for line in lines[1:]:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) != 3:
            raise ValueError("Invalid CSV row")
        if parts[0].lower() not in allowed_days:
            raise ValueError("Invalid weekday")
        hm = parts[1].split(":")
        if len(hm) != 2:
            raise ValueError("Invalid start time")
        hour, minute = int(hm[0]), int(hm[1])
        seconds = int(parts[2])
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 1 <= seconds <= 86400):
            raise ValueError("Invalid time or duration")
        count += 1
    return count


def _replace_schedule(csv_text):
    """Keep a backup so an interrupted replacement can be recovered."""
    with open("schedule.tmp", "w") as f:
        f.write(csv_text)

    with open("schedule.tmp", "r") as f:
        _validate_csv(f.read())

    had_old = False
    try:
        os.remove("schedule.bak")
    except OSError:
        pass

    try:
        os.rename("schedule.csv", "schedule.bak")
        had_old = True
    except OSError:
        pass

    try:
        os.rename("schedule.tmp", "schedule.csv")
    except Exception:
        if had_old:
            try:
                os.rename("schedule.bak", "schedule.csv")
            except Exception:
                pass
        raise


def _recover_schedule_file():
    try:
        with open("schedule.csv", "r") as f:
            _validate_csv(f.read())
        return
    except Exception:
        pass
    try:
        with open("schedule.bak", "r") as f:
            backup = f.read()
        _validate_csv(backup)
        with open("schedule.csv", "w") as f:
            f.write(backup)
    except Exception:
        pass


def _file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def sync_once(wlan):
    """Perform one schedule sync and heartbeat check. Safe to call from worker thread."""
    global _schedule_update_pending

    if not wlan.isconnected():
        return False

    version_data = _http_request("GET", API_BASE.rstrip('/') + "/device/version/")
    server_version = int(json.loads(version_data)["version"])
    local_version = _read_local_version()

    if server_version != local_version or not _file_exists("schedule.csv"):
        csv_text = _http_request("GET", API_BASE.rstrip('/') + "/device/schedule.csv")
        _replace_schedule(csv_text)
        _write_local_version(server_version)
        with _sync_lock:
            _schedule_update_pending = True
        print("Schedule updated from server. Version:", server_version)

    _http_request("POST", API_BASE.rstrip('/') + "/device/heartbeat/", {
        "device_id": DEVICE_ID,
        "version": server_version
    })
    return True


def _worker(wlan):
    wlan.active(True)
    _recover_schedule_file()

    while True:
        try:
            sync_once(wlan)
        except Exception as exc:
            print("Schedule sync error:", exc)
        time.sleep(POLL_SECONDS)


def start_sync_worker(wlan=None):
    """Start background sync thread (only if no other thread is running on Core 1)."""
    if wlan is None:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
    _thread.start_new_thread(_worker, (wlan,))


def take_schedule_update():
    """Call from main loop; True means call load_schedule() now."""
    global _schedule_update_pending
    with _sync_lock:
        pending = _schedule_update_pending
        _schedule_update_pending = False
    return pending
