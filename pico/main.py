import machine
import time
import network
import ntptime
import _thread
from machine import Pin, I2C

# =====================================================
# CONFIGURATION - EDIT THESE VALUES
# =====================================================

WIFI_SSID = "PT SOLAR"
WIFI_PASSWORD = "tcf@praful"

API_BASE_URL = "http://66.116.251.98:8012/api"
DEVICE_API_KEY = "dev-device-key-67890"
DEVICE_ID = "pico-w-01"

SYNC_INTERVAL = 60       # Check server every 60 seconds
IST_OFFSET = 19800       # UTC + 5:30

SCHEDULE_FILE = "schedule.csv"

# Manual GP9 button: duration per relay (Relays 1-6)
MANUAL_RELAY_SECONDS = 2

# Relay GPIO pins: R1..R7
RELAY_PINS = [2, 3, 4, 5, 6, 7, 8]

# Relays 1-6 are active LOW; Relay 7 is active HIGH
BUTTON_PIN = 9
RTC_ADDRESS = 0x68

# =====================================================
# INITIALIZE RELAYS FIRST - ALL OFF
# =====================================================

relays = []

for index, gpio in enumerate(RELAY_PINS):
    relay = Pin(gpio, Pin.OUT)
    relay.value(1 if index < 6 else 0)
    relays.append(relay)


def relay_on(index):
    relays[index].value(0 if index < 6 else 1)


def relay_off(index):
    relays[index].value(1 if index < 6 else 0)


def all_relays_off():
    for i in range(7):
        relay_off(i)


# =====================================================
# BUTTON
# =====================================================

button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

# =====================================================
# I2C AND DS3231
# =====================================================

i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000)

devices = i2c.scan()
print("I2C devices:", [hex(x) for x in devices])

rtc_available = RTC_ADDRESS in devices
if not rtc_available:
    print("ERROR: DS3231 not detected. Relay manual operation remains available.")


def dec_to_bcd(value):
    return ((value // 10) << 4) | (value % 10)


def bcd_to_dec(value):
    return ((value >> 4) * 10) + (value & 0x0F)


DAYS = {
    1: "Sunday",
    2: "Monday",
    3: "Tuesday",
    4: "Wednesday",
    5: "Thursday",
    6: "Friday",
    7: "Saturday"
}

DAY_NUMBERS = {
    "sunday": 1,
    "monday": 2,
    "tuesday": 3,
    "wednesday": 4,
    "thursday": 5,
    "friday": 6,
    "saturday": 7
}


def read_rtc():
    if not rtc_available:
        raise OSError("DS3231 is not available")

    data = i2c.readfrom_mem(RTC_ADDRESS, 0x00, 7)

    second = bcd_to_dec(data[0] & 0x7F)
    minute = bcd_to_dec(data[1] & 0x7F)

    # Supports both 12-hour and 24-hour DS3231 formats.
    if data[2] & 0x40:
        hour = bcd_to_dec(data[2] & 0x1F)
        is_pm = bool(data[2] & 0x20)
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
    else:
        hour = bcd_to_dec(data[2] & 0x3F)

    weekday = data[3] & 0x07
    day = bcd_to_dec(data[4] & 0x3F)
    month = bcd_to_dec(data[5] & 0x1F)
    year = 2000 + bcd_to_dec(data[6])

    return year, month, day, weekday, hour, minute, second


def write_rtc(year, month, day, weekday, hour, minute, second):
    if not rtc_available:
        return

    values = bytearray([
        dec_to_bcd(second),
        dec_to_bcd(minute),
        dec_to_bcd(hour),
        weekday,
        dec_to_bcd(day),
        dec_to_bcd(month),
        dec_to_bcd(year % 100)
    ])
    i2c.writeto_mem(RTC_ADDRESS, 0x00, values)


def display_rtc():
    try:
        y, m, d, wd, h, mi, s = read_rtc()
        print("{:02d}-{:02d}-{:04d} | {} | {:02d}:{:02d}:{:02d}".format(
            d, m, y, DAYS.get(wd, "Unknown"), h, mi, s
        ))
    except Exception as exc:
        print("RTC read error:", exc)


# =====================================================
# SHARED WI-FI INTERFACE
# =====================================================

wifi_configured = bool(
    WIFI_SSID and WIFI_SSID != "YOUR_WIFI_NAME"
    and WIFI_PASSWORD and WIFI_PASSWORD != "YOUR_WIFI_PASSWORD"
)

wlan = network.WLAN(network.STA_IF)
if wifi_configured:
    wlan.active(True)
else:
    print("Wi-Fi credentials not configured; offline mode only.")

ntp_sync_pending = False
pico_sync = None


def network_worker():
    """Background worker on Core 1: manages Wi-Fi, NTP sync, and server schedule sync."""
    global ntp_sync_pending

    ntptime.host = "pool.ntp.org"
    last_ntp_sync = None
    last_schedule_sync = None
    connection_attempt_started = False

    while True:
        try:
            if not wlan.isconnected():
                if not connection_attempt_started:
                    print("Connecting Pico W to Wi-Fi...")
                    try:
                        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                    except Exception as exc:
                        print("Wi-Fi connect request:", exc)
                    connection_attempt_started = True

                wait_count = 0
                while not wlan.isconnected() and wait_count < 10:
                    time.sleep(1)
                    wait_count += 1

                if not wlan.isconnected():
                    print("Wi-Fi unavailable; continuing with DS3231/local CSV.")
                    connection_attempt_started = False
                    time.sleep(15)
                    continue

            connection_attempt_started = False

            now = time.ticks_ms()

            # 1. Sync DS3231 with NTP every 6 hours
            if last_ntp_sync is None or time.ticks_diff(now, last_ntp_sync) >= 21600000:
                try:
                    ntptime.settime()
                    ntp_sync_pending = True
                    last_ntp_sync = time.ticks_ms()
                    print("NTP synchronization successful; DS3231 update pending.")
                except Exception as exc:
                    print("NTP error; retaining DS3231 time:", exc)

            # 2. Sync schedule and send heartbeat to VPS every SYNC_INTERVAL (60s)
            if pico_sync is not None:
                schedule_due = (
                    last_schedule_sync is None
                    or time.ticks_diff(now, last_schedule_sync) >= (SYNC_INTERVAL * 1000)
                )
                if schedule_due:
                    try:
                        pico_sync.sync_once(wlan)
                        last_schedule_sync = time.ticks_ms()
                    except Exception as exc:
                        print("Schedule sync error:", exc)

            time.sleep(2)

        except Exception as exc:
            print("Network worker error:", exc)
            connection_attempt_started = False
            time.sleep(10)


def update_rtc_from_ntp():
    try:
        utc_time = time.time()
        ist_time = time.localtime(utc_time + IST_OFFSET)

        year, month, day = ist_time[0], ist_time[1], ist_time[2]
        hour, minute, second = ist_time[3], ist_time[4], ist_time[5]

        # MicroPython weekday: Monday=0..Sunday=6
        # DS3231 weekday: Sunday=1..Saturday=7
        weekday = ((ist_time[6] + 1) % 7) + 1

        write_rtc(year, month, day, weekday, hour, minute, second)
        print("DS3231 updated from NTP using IST.")
    except Exception as exc:
        print("DS3231 NTP update error:", exc)


# =====================================================
# LOAD AND VALIDATE LOCAL CSV
# =====================================================

schedule = []


def parse_schedule_text(csv_text):
    parsed = []

    for line_number, line in enumerate(csv_text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        if line.lower().replace(" ", "") == "day,starttime,sec":
            continue

        parts = line.split(",")
        if len(parts) != 3:
            raise ValueError("Invalid CSV row {}".format(line_number))

        day_name = parts[0].strip().lower()
        start_time = parts[1].strip()
        seconds_text = parts[2].strip()

        if day_name not in DAY_NUMBERS:
            raise ValueError("Invalid day in CSV row {}".format(line_number))

        time_parts = start_time.split(":")
        if len(time_parts) != 2:
            raise ValueError("Invalid time in CSV row {}".format(line_number))

        hour = int(time_parts[0])
        minute = int(time_parts[1])
        seconds = int(seconds_text)

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time in CSV row {}".format(line_number))
        if not (1 <= seconds <= 86400):
            raise ValueError("Invalid seconds in CSV row {}".format(line_number))

        parsed.append((DAY_NUMBERS[day_name], hour, minute, seconds))

    return parsed


def load_schedule():
    global schedule

    try:
        with open(SCHEDULE_FILE, "r") as file:
            csv_text = file.read()

        new_schedule = parse_schedule_text(csv_text)
        schedule = new_schedule

        print("Loaded schedule entries:", len(schedule))
        for item in schedule:
            print(item)

        return True

    except Exception as exc:
        print("Schedule load failed; retaining current schedule:", exc)
        return False


load_schedule()

# =====================================================
# START UNIFIED BACKGROUND NETWORK WORKER
# =====================================================

if wifi_configured:
    try:
        import pico_sync as _pico_sync
        pico_sync = _pico_sync
        pico_sync.configure(
            api_base=API_BASE_URL,
            api_key=DEVICE_API_KEY,
            device_id=DEVICE_ID,
            poll_seconds=SYNC_INTERVAL
        )
        print("Schedule synchronizer configured.")
    except Exception as exc:
        print("Could not load pico_sync:", exc)

    # Starts single background thread on Core 1 for both NTP & Schedule Sync
    _thread.start_new_thread(network_worker, ())
    print("Background network worker started.")
else:
    print("NTP and online schedule sync disabled; using local DS3231 + CSV.")


# =====================================================
# COMMON RELAY SEQUENCE
# =====================================================

cycle_active = False
current_relay = 0
relay_start_time = 0
active_duration_ms = 0


def start_sequence(duration_seconds, source):
    global cycle_active
    global current_relay
    global relay_start_time
    global active_duration_ms

    if cycle_active or duration_seconds <= 0:
        return False

    all_relays_off()

    active_duration_ms = duration_seconds * 1000

    relay_on(6)       # Master relay 7 ON
    current_relay = 0
    relay_on(0)       # Relay 1 ON

    relay_start_time = time.ticks_ms()
    cycle_active = True

    print("{} sequence started; each relay ON for {} seconds.".format(
        source, duration_seconds
    ))
    return True


def process_sequence():
    global cycle_active
    global current_relay
    global relay_start_time

    if not cycle_active:
        return

    now = time.ticks_ms()

    if time.ticks_diff(now, relay_start_time) >= active_duration_ms:
        relay_off(current_relay)
        current_relay += 1

        if current_relay < 6:
            relay_on(current_relay)
            relay_start_time = now
            print("Relay {} ON".format(current_relay + 1))
        else:
            relay_off(6)
            all_relays_off()
            cycle_active = False
            print("Sequence completed. All relays OFF.")


# =====================================================
# WEEKLY SCHEDULER
# =====================================================

fired_events = set()
current_schedule_date = None
scheduled_queue = []


def check_schedule(rtc_data):
    global current_schedule_date
    global fired_events
    global scheduled_queue

    year, month, day, weekday, hour, minute, second = rtc_data
    today = (year, month, day)

    if today != current_schedule_date:
        current_schedule_date = today
        fired_events = set()

    for item in schedule:
        scheduled_day, scheduled_hour, scheduled_minute, seconds = item
        event_key = (today, item)

        if event_key in fired_events:
            continue

        if (
            weekday == scheduled_day
            and hour == scheduled_hour
            and minute == scheduled_minute
        ):
            fired_events.add(event_key)
            scheduled_queue.append(seconds)

            print(
                "Scheduled event:",
                DAYS[weekday],
                "{:02d}:{:02d}".format(hour, minute),
                seconds,
                "seconds per relay"
            )


# =====================================================
# MAIN LOOP
# =====================================================

last_button_raw = 1
stable_button_state = 1
last_button_change = time.ticks_ms()

DEBOUNCE_MS = 40
last_rtc_check = time.ticks_ms()
last_display = time.ticks_ms()

print("Controller started.")
print("Waiting for GP9 button or weekly schedule...")

while True:
    now = time.ticks_ms()

    # Apply NTP updates to DS3231 on main thread safely
    if ntp_sync_pending:
        ntp_sync_pending = False
        update_rtc_from_ntp()

    # Check for downloaded schedule CSV updates
    if pico_sync is not None:
        try:
            if pico_sync.take_schedule_update():
                if load_schedule():
                    print("New server schedule is now active.")
        except Exception as exc:
            print("Schedule update notification error:", exc)

    # Read DS3231 and check weekly schedule every 500ms
    if rtc_available and time.ticks_diff(now, last_rtc_check) >= 500:
        last_rtc_check = now
        try:
            rtc_data = read_rtc()
            check_schedule(rtc_data)
        except Exception as exc:
            print("RTC/scheduler error:", exc)

    # Periodic RTC print every 30s
    if time.ticks_diff(now, last_display) >= 30000:
        last_display = now
        if rtc_available:
            display_rtc()

    # Button debounce
    raw_state = button.value()

    if raw_state != last_button_raw:
        last_button_raw = raw_state
        last_button_change = now

    if time.ticks_diff(now, last_button_change) >= DEBOUNCE_MS:
        if raw_state != stable_button_state:
            stable_button_state = raw_state

            if stable_button_state == 0:
                if not cycle_active and not scheduled_queue:
                    start_sequence(MANUAL_RELAY_SECONDS, "Manual")
                else:
                    print("Controller busy. Button request ignored.")

    process_sequence()

    if not cycle_active and scheduled_queue:
        duration = scheduled_queue.pop(0)
        start_sequence(duration, "Scheduled")

    time.sleep_ms(5)
