# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ESPHome Logger — a Python async application that connects to ESPHome devices via their native API and logs all sensor state changes to daily CSV files.

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Multi-device logger (production use)
python main.py

# Single-device debug logger (prints raw state objects)
python simple.py
```

Requires a `.env` file with device host/password pairs (e.g., `API_HOST_SEWAGE_TANK`, `API_SEWAGE_TANK_PASSWORD`). See README.md for full `.env` format.

## Architecture

- **esphome_logger.py** — Core `ESPHomeLogger` class. Handles connection, reconnection, entity discovery, state subscription, and CSV writing. Uses `aioesphomeapi` for ESPHome native API communication. All timestamps use Eastern time (`America/New_York`).
- **main.py** — Entry point. Loads `.env`, creates one `ESPHomeLogger` per device, runs them concurrently via `asyncio.gather`.
- **simple.py** — Minimal single-device script for testing. Connects directly with `APIClient` and prints raw state updates (no CSV logging).

Key design details:
- CSV files rotate daily, stored under `logs/<device-name>/esphome_YYYY-MM-DD.csv`
- Connection health is monitored with a 5-minute timeout; if no activity, it forces reconnect
- NaN and None values are filtered out before logging
- The `password` parameter is used for both `password` and `noise_psk` in `APIClient`
