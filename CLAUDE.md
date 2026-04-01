# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ESPHome Logger — a Python async application that connects to ESPHome devices via their native API, logs all sensor state changes to daily CSV files, captures device logs, optionally uploads data to Google Drive, and optionally writes to InfluxDB for visualization with Grafana.

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Multi-device logger (production use)
python main.py

# Single-device debug logger (prints raw state objects)
python simple.py

# Upload latest CSVs to Google Drive
python upload_to_drive.py
```

Requires a `.env` file — see Environment Variables section below.

## Architecture

- **esphome_logger.py** — Core `ESPHomeLogger` class. Handles connection, reconnection, entity discovery, state subscription, device log subscription, CSV writing, and optional InfluxDB writes. Uses `aioesphomeapi` for ESPHome native API communication. All timestamps use Eastern time (`America/New_York`). Contains `InfluxConfig` dataclass for InfluxDB configuration.
- **main.py** — Entry point. Loads `.env`, auto-discovers devices from `API_HOST_*` environment variables, creates one `ESPHomeLogger` per device, runs them concurrently via `asyncio.gather`.
- **simple.py** — Minimal single-device script for testing. Connects directly with `APIClient` and prints raw state updates (no CSV logging).
- **upload_to_drive.py** — Standalone script that combines the 2 newest CSV files per device and uploads to Google Drive via OAuth2. Designed to run on a schedule (e.g., cron).
- **esphome-logger.service** — systemd unit file for running the logger as a service on Raspberry Pi.

### Key design details

- CSV files rotate daily, stored under `logs/<device-name>/esphome_YYYY-MM-DD.csv`
- Device logs are captured via `subscribe_logs()` at VERY_VERBOSE level, written to `logs/<device-name>/esphome_YYYY-MM-DD.log` with ANSI escape codes stripped
- Connection health is monitored by tracking `last_activity` (updated on every state change and log message); if no activity for 5 minutes, it disconnects and reconnects
- The client is explicitly disconnected before reconnecting to avoid "Already connected" errors
- NaN and None values are filtered out before logging
- The `password` parameter is used for both `password` and `noise_psk` in `APIClient`
- Old CSV and log files are deleted based on `LOG_RETENTION_DAYS`
- InfluxDB writes are optional — enabled only when `INFLUXDB_URL` is set in `.env`. Uses measurement `sensor_state` with tags `host`, `entity_id`, `friendly_name`. Numeric values go to field `value` (float); non-numeric to `value_str` (string). Write failures are logged as warnings and never crash the logger.

## Environment Variables (`.env`)

```bash
# Device configuration — one pair per device
API_HOST_SEWAGE_TANK=sewage-tank-sensor.local
API_SEWAGE_TANK_PASSWORD=

# Log settings
LOG_DIR=logs
LOG_RETENTION_DAYS=14

# Google Drive upload (used by upload_to_drive.py)
GOOGLE_DRIVE_FOLDER_ID=<folder-id-from-drive-url>
GOOGLE_OAUTH_CREDENTIALS_FILE=credentials.json

# InfluxDB 2.x (optional — remove or leave blank to disable)
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-influxdb-api-token-here
INFLUXDB_ORG=home
INFLUXDB_BUCKET=esphome
```

Device discovery: `main.py` scans for all `API_HOST_<NAME>` variables and looks up `API_<NAME>_PASSWORD` for each.

## Google Drive Upload Setup

1. Create a Google Cloud project and enable the Google Drive API
2. Configure the OAuth consent screen (External, add yourself as a test user)
3. Create an OAuth 2.0 Client ID (Desktop app), download as `credentials.json`
4. Run `python upload_to_drive.py` — a browser window opens for one-time login
5. After login, `token.json` is saved for future runs (auto-refreshes)
6. Both `credentials.json` and `token.json` are in `.gitignore`

The upload script combines the 2 most recent CSV files per device into one file and uploads it as `<device-name>.csv` to the specified Google Drive folder. If the file already exists, it updates in place.

## InfluxDB + Grafana Setup

### Install InfluxDB 2.x on Raspberry Pi

```bash
curl -s https://repos.influxdata.com/influxdata-archive_compat.key \
  | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata.gpg > /dev/null
echo "deb [signed-by=/etc/apt/trusted.gpg.d/influxdata.gpg] https://repos.influxdata.com/debian stable main" \
  | sudo tee /etc/apt/sources.list.d/influxdata.list
sudo apt update && sudo apt install -y influxdb2
sudo systemctl enable --now influxdb
# Verify running
curl http://localhost:8086/health
```

Initial setup (or use the web UI at `http://<pi-ip>:8086`):

```bash
influx setup \
  --username admin \
  --password <your-password> \
  --org home \
  --bucket esphome \
  --retention 0 \
  --force

# Create an API token for the logger
influx auth create --org home --all-access --description "ESPHome Logger"
# Copy the printed token into INFLUXDB_TOKEN in .env
```

### Install Grafana on Raspberry Pi

```bash
wget -q -O - https://apt.grafana.com/gpg.key \
  | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/trusted.gpg.d/grafana.gpg] https://apt.grafana.com stable main" \
  | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update && sudo apt install -y grafana
sudo systemctl enable --now grafana-server
# Access at http://<pi-ip>:3000 (default login: admin/admin)
```

### Add InfluxDB as a Grafana data source

1. Go to **Connections > Data Sources > Add data source > InfluxDB**
2. Set **Query Language** to **Flux**
3. URL: `http://localhost:8086`
4. Organisation: `home`, Token: (from above), Default Bucket: `esphome`
5. Click **Save & Test**

### Example Flux query for a Grafana panel

```flux
from(bucket: "esphome")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "sensor_state")
  |> filter(fn: (r) => r._field == "value")
  |> filter(fn: (r) => r.host == "sewage-tank-sensor.local")
```

Grafana will automatically split results into separate series per `friendly_name` tag.

## Raspberry Pi Deployment

Target: Raspbian GNU/Linux 13 (trixie)

### Initial setup

```bash
# Clone the repo
cd ~/GitHub
git clone <repo-url> ESPHome-Logger
cd ESPHome-Logger

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy .env, credentials.json, and token.json from dev machine
# token.json is portable — works on any machine with the same credentials.json
```

### Running as a systemd service

```bash
sudo cp esphome-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable esphome-logger
sudo systemctl start esphome-logger

# Useful commands
sudo systemctl status esphome-logger
journalctl -u esphome-logger -f
sudo systemctl restart esphome-logger
```

The service file assumes the repo is at `/home/pi/GitHub/ESPHome-Logger` with a venv. Edit paths in the `.service` file if different.

### Scheduled Google Drive upload (cron)

```bash
crontab -e
# Add this line for hourly uploads:
0 * * * * cd /home/pi/GitHub/ESPHome-Logger && /home/pi/GitHub/ESPHome-Logger/venv/bin/python upload_to_drive.py >> /var/log/pi/ESPHomeLogs/upload.log 2>&1
```
