# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ESPHome Logger — a Python async application that connects to ESPHome devices via their native API, logs all sensor state changes to daily CSV files, captures device logs, and optionally uploads data to Google Drive.

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

- **esphome_logger.py** — Core `ESPHomeLogger` class. Handles connection, reconnection, entity discovery, state subscription, device log subscription, and CSV writing. Uses `aioesphomeapi` for ESPHome native API communication. All timestamps use Eastern time (`America/New_York`).
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
