"""Pico W background schedule synchronizer.

Copy this file to the Pico. Requires MicroPython on Pico W and urequests.py
(or a compatible requests module) on the device filesystem.
The caller must call take_schedule_update() in the main loop and then reload
its in-memory schedule with its existing load_schedule() function.
"""
import time
import network
import _thread
import os

try:
    import urequests as requests
except ImportError:
    import requests

# Set these values before use.
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
API_BASE = "http://66.116.251.98:8012/api"
DEVICE_API_KEY = "dev-device-key-67890"
DEVICE_ID = "pico-w-01"
POLL_SECONDS = 60

_schedule_update_pending = False
_sync_lock = _thread.allocate_lock()


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

    # Validate the actual saved file before replacing the current schedule.
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
    # Recover from power loss during file replacement.
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


def _get(url):
    response = requests.get(url, headers={"X-API-Key": DEVICE_API_KEY})
    try:
        if response.status_code != 200:
            raise Exception("HTTP status: {}".format(response.status_code))
        return response.text
    finally:
        response.close()


def _post(url, payload):
    response = requests.post(
        url,
        json=payload,
        headers={"X-API-Key": DEVICE_API_KEY},
    )
    try:
        if response.status_code not in (200, 201):
            raise Exception("HTTP status: {}".format(response.status_code))
    finally:
        response.close()


def _sync_once(wlan):
    global _schedule_update_pending

    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        wait = 0
        while not wlan.isconnected() and wait < 15:
            time.sleep(1)
            wait += 1

    if not wlan.isconnected():
        print("Schedule sync: Wi-Fi unavailable; using local CSV")
        return

    version_data = _get(API_BASE + "/device/version/")
    # Avoid importing json globally in the main relay program.
    import ujson
    server_version = int(ujson.loads(version_data)["version"])
    local_version = _read_local_version()

    if server_version != local_version or not _file_exists("schedule.csv"):
        csv_text = _get(API_BASE + "/device/schedule.csv")
        _replace_schedule(csv_text)
        _write_local_version(server_version)
        with _sync_lock:
            _schedule_update_pending = True
        print("Schedule updated from server. Version:", server_version)

    _post(API_BASE + "/device/heartbeat/", {
        "device_id": DEVICE_ID,
        "version": server_version
    })


def _file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _worker(wlan):
    # Reuse the controller's shared WLAN interface; do not create a second
    # independent Wi-Fi reconnect manager when NTP is already running.
    wlan.active(True)
    _recover_schedule_file()

    while True:
        try:
            _sync_once(wlan)
        except Exception as exc:
            print("Schedule sync error:", exc)
        time.sleep(POLL_SECONDS)


def start_sync_worker(wlan=None):
    """Call once after initializing relays and local schedule.

    Pass the same WLAN object used by the existing NTP worker. If omitted,
    this module creates its own interface (only do this if no other worker
    manages Wi-Fi).
    """
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
