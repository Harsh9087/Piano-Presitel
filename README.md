# Relay Schedule Manager

React dashboard + Django REST API + SQLite for a Raspberry Pi Pico W weekly relay scheduler. No Docker.

## Features
- Weekly schedule CRUD (day, HH:MM, seconds per relay 1-6, enabled/disabled)
- CSV endpoint for the Pico: `GET /api/device/schedule.csv`
- Schedule version endpoint: `GET /api/device/version/`
- Device heartbeat: `POST /api/device/heartbeat/`
- Dashboard API key and separate device API key
- SQLite database; CSV is generated from enabled schedules

## Important safety / design
- The VPS does not switch relays. The Pico executes schedules locally from DS3231 + its last valid CSV.
- Pico should download to `schedule.tmp`, validate it, then replace `schedule.csv` only after successful validation.
- Poll version every 60 seconds; download CSV only if version differs.
- Keep the existing manual relay sequence in the Pico firmware. Both manual and scheduled triggers call the same sequence function.
- Schedule time is Asia/Kolkata. CSV weekday names are Monday through Sunday.
- `sec` means ON time for EACH relay 1–6; total sequence time is `6 * sec` seconds.

## Local development

### Backend
```bash
cd backend
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set strong random keys
python manage.py makemigrations scheduler
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The Vite dev server needs a proxy to the backend for local development; add this to `vite.config.js` if using separate ports:
```js
server: { proxy: { '/api': 'http://127.0.0.1:8000' } }
```

## Docker Deployment (Recommended)

To deploy with Docker on your VPS without needing to install Python 3.12, Node.js, or Nginx on the host:

1. Allow port `8012` on the VPS:
   ```bash
   sudo firewall-cmd --permanent --add-port=8012/tcp && sudo firewall-cmd --reload
   # or with ufw: sudo ufw allow 8012/tcp
   ```
2. Clone this repo:
   ```bash
   git clone https://github.com/Harsh9087/Piano-Presitel.git /opt/relay-scheduler
   cd /opt/relay-scheduler
   ```
3. Create your `.env` configuration:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env to set your API keys
   ```
4. Start the container:
   ```bash
   docker compose up -d --build
   ```
5. View logs or check status:
   ```bash
   docker compose logs -f
   docker compose ps
   ```
The dashboard is accessible at `http://<VPS_IP>:8012` and Pico W endpoints at `http://<VPS_IP>:8012/api/`. Data is automatically persisted in the `./data` directory.

## Manual VPS deployment (bare-metal)
Do not run this until you have confirmed the chosen domain and checked that port 8012 is unused. These steps create a new app directory/service and a separate Nginx server block; they do not require Docker or changes to existing application containers.

1. Check the server OS, current services, ports and Nginx configuration before changing anything:
```bash
cat /etc/os-release
sudo ss -lntp
sudo systemctl --type=service --state=running
sudo nginx -T > ~/nginx-before-relay-scheduler.txt
```
2. Choose an unused service port (default example: 8012) and a subdomain. Point the subdomain DNS A record to the VPS IP.
3. Copy this project to `/opt/relay-scheduler`. Create a dedicated Linux user `relayapp`, own the app directory by that user, and create a venv.
4. Install backend requirements, create `.env` from `.env.example`, and set unique strong values for `DJANGO_SECRET_KEY`, `DASHBOARD_API_KEY`, `DEVICE_API_KEY`, `DJANGO_ALLOWED_HOSTS`. Never reuse the Pico API key as the dashboard key.
5. Run:
```bash
cd /opt/relay-scheduler/backend
/opt/relay-scheduler/venv/bin/python manage.py makemigrations scheduler
/opt/relay-scheduler/venv/bin/python manage.py migrate
/opt/relay-scheduler/venv/bin/python manage.py collectstatic --noinput
```
6. Build React on the VPS (Node.js required):
```bash
cd /opt/relay-scheduler/frontend
npm ci
npm run build
```
7. Copy `deploy/gunicorn.service.example` to `/etc/systemd/system/relay-scheduler.service`, review user/path/port, then `systemctl daemon-reload`, `systemctl enable --now relay-scheduler`.
8. Create a NEW Nginx config file from `deploy/nginx.conf.example`, replace `schedule.example.com`, enable only that new site, run `nginx -t`, and reload Nginx only if the test passes.
9. Configure HTTPS for the new subdomain using your existing certificate workflow or Certbot. Do not change existing TLS server blocks.
10. Verify `/api/device/version/` with the device key and the dashboard using the dashboard key.

## API quick reference
All API keys are sent as `X-API-Key`.

Dashboard:
- `GET /api/schedules/`
- `POST /api/schedules/` JSON: `{"day":0,"start_time":"05:00","seconds":120,"enabled":true}`
- `PUT /api/schedules/<id>/`
- `DELETE /api/schedules/<id>/`
- `GET /api/dashboard/status/`

Pico device:
- `GET /api/device/version/`
- `GET /api/device/schedule.csv`
- `POST /api/device/heartbeat/` JSON: `{"device_id":"pico-w-01","version":3}`

`day` uses Python weekday numbering: Monday=0 ... Sunday=6. CSV uses names.

## Pico W sync integration

Copy `pico/pico_sync.py` to the Pico filesystem. Set `WIFI_SSID`, `WIFI_PASSWORD`, `API_BASE`, and `DEVICE_API_KEY` in that file. Ensure a compatible `urequests.py` library is also on the Pico filesystem (or that your firmware provides `requests`).

In your existing relay controller `main.py`:

1. Keep the current relay initialization, DS3231 logic, `load_schedule()`, and common relay sequence logic.
2. Import and start the synchronizer after the local schedule has been loaded:
```python
import pico_sync
pico_sync.start_sync_worker(wlan)
```
Here `wlan` must be the same `network.WLAN(network.STA_IF)` object used by your existing NTP worker. If your current NTP worker creates `wlan` as a local variable, move WLAN initialization to shared/global scope and have both workers use that object. Do not run two independent Wi-Fi reconnect managers.

3. In the main loop, check for a completed update and reload the in-memory schedule:
```python
if pico_sync.take_schedule_update():
    load_schedule()
```

The network work runs in a background thread. It does not access I2C or control relay GPIO. It writes and validates `schedule.tmp`, retains a backup, then replaces the local CSV. The main loop reloads the in-memory schedule after the worker signals a successful update.

The first successful sync downloads the CSV even if the local version file is absent. The Pico sends a heartbeat after successful version checking. If Wi-Fi or the API is unavailable, the existing local CSV remains in use.
