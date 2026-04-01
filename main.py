import asyncio
from esphome_logger import ESPHomeLogger, InfluxConfig, log, setup_logging
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Log directory base path
LOG_DIR = os.getenv("LOG_DIR", "logs")
setup_logging(LOG_DIR)

# Log retention (days) - set to None to keep all logs
LOG_RETENTION_DAYS = os.getenv("LOG_RETENTION_DAYS")
if LOG_RETENTION_DAYS is not None:
    LOG_RETENTION_DAYS = int(LOG_RETENTION_DAYS)

# InfluxDB configuration (optional)
_influx_cfg: InfluxConfig | None = None
_influx_url = os.getenv("INFLUXDB_URL", "").strip()
if _influx_url:
    _influx_cfg = InfluxConfig(
        url=_influx_url,
        token=os.getenv("INFLUXDB_TOKEN", ""),
        org=os.getenv("INFLUXDB_ORG", ""),
        bucket=os.getenv("INFLUXDB_BUCKET", "esphome"),
    )
    log(f"InfluxDB configured: {_influx_url}")


def discover_devices():
    """Discover devices from API_HOST_* environment variables.

    For each API_HOST_<DEVICE_NAME>, looks up API_<DEVICE_NAME>_PASSWORD.
    The subdirectory name is derived by lowercasing and replacing underscores with hyphens.
    """
    devices = []
    for key, value in os.environ.items():
        if key.startswith("API_HOST_") and value:
            device_name = key.removeprefix("API_HOST_")
            password = os.getenv(f"API_{device_name}_PASSWORD", "")
            subdir = device_name.lower().replace("_", "-")
            devices.append({
                "host": value,
                "password": password,
                "csv_dir": os.path.join(LOG_DIR, subdir),
                "retention_days": LOG_RETENTION_DAYS,
                "influx_cfg": _influx_cfg,
            })
    return devices


async def main():
    devices = discover_devices()
    if not devices:
        log("No devices found. Add API_HOST_<DEVICE_NAME> entries to .env")
        return
    log(f"Discovered {len(devices)} device(s): {', '.join(str(d['host']) for d in devices)}")
    loggers = [ESPHomeLogger(**dev) for dev in devices]
    await asyncio.gather(*(logger.run() for logger in loggers))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Shutting down")
