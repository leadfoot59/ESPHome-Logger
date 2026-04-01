import asyncio
import csv
import dataclasses
import glob
from math import isnan
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aioesphomeapi import APIClient
from aioesphomeapi.core import APIConnectionError
from aioesphomeapi.model import LogLevel

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    _INFLUXDB_AVAILABLE = True
except ImportError:
    _INFLUXDB_AVAILABLE = False

EASTERN = ZoneInfo("America/New_York")

_log_dir: str | None = None

def setup_logging(log_dir: str) -> None:
    global _log_dir
    _log_dir = log_dir
    os.makedirs(log_dir, exist_ok=True)

def log(msg: str) -> None:
    ts = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_dir is not None:
        log_file = os.path.join(_log_dir, "esphome_logger.log")
        with open(log_file, "a") as f:
            f.write(line + "\n")


@dataclasses.dataclass
class InfluxConfig:
    url: str
    token: str
    org: str
    bucket: str


# ESPHomeLogger class
class ESPHomeLogger:
    def __init__(self, host: str, password: str | None = None, csv_dir: str = "logs", retry_interval: int = 15, retention_days: int | None = None, influx_cfg: InfluxConfig | None = None):
        self.host = host
        self.client = APIClient(host, 6053, password=password, noise_psk=password)
        self.csv_dir = csv_dir
        self.current_date: str | None = None
        self.csv_file: str = ""
        self.entity_map: dict[int, str] = {}
        self.retry_interval = retry_interval
        self.retention_days = retention_days
        self.connected = False
        self.last_activity: datetime | None = None

        self._influx_client = None
        self._influx_write_api = None
        self._influx_bucket: str = ""
        self._influx_org: str = ""

        if influx_cfg is not None:
            if not _INFLUXDB_AVAILABLE:
                log("WARNING: INFLUXDB_URL is set but influxdb-client is not installed. InfluxDB writes disabled.")
            else:
                self._influx_client = InfluxDBClient(
                    url=influx_cfg.url,
                    token=influx_cfg.token,
                    org=influx_cfg.org,
                )
                self._influx_write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)
                self._influx_bucket = influx_cfg.bucket
                self._influx_org = influx_cfg.org
                log(f"InfluxDB enabled for {self.host} -> {influx_cfg.url}/{influx_cfg.bucket}")

        os.makedirs(csv_dir, exist_ok=True)

    # Get the CSV file for the current date
    def _get_csv_file(self):
        today = datetime.now(EASTERN).date().isoformat()
        if today != self.current_date:
            self.current_date = today
            self.csv_file = os.path.join(self.csv_dir, f"esphome_{today}.csv")
            if not os.path.exists(self.csv_file):
                with open(self.csv_file, "w", newline="") as f:
                    csv.writer(f).writerow(["timestamp", "entity_id", "friendly_name", "state"])
            self._delete_old_logs()
        return self.csv_file

    # Connect to the ESPHome device
    async def connect(self):
        try:
            await self.client.connect(login=True)
            entities, _ = await self.client.list_entities_services()
            self.entity_map = {ent.key: ent.name for ent in entities}
            self.client.subscribe_states(self._state_callback)
            self.client.subscribe_logs(self._log_callback, log_level=LogLevel.LOG_LEVEL_VERY_VERBOSE)
            self.connected = True
            self.last_activity = datetime.now(EASTERN)
            log(f"Successfully connected to {self.host}")
        except APIConnectionError as e:
            self.connected = False
            log(f"Connection failed to {self.host}: {e}")
            raise
        except Exception as e:
            self.connected = False
            log(f"Unexpected error connecting to {self.host}: {e}")
            raise

    # Get the device log file for the current date
    def _get_log_file(self) -> str:
        today = datetime.now(EASTERN).date().isoformat()
        return os.path.join(self.csv_dir, f"esphome_{today}.log")

    # Device log callback
    def _log_callback(self, msg) -> None:
        self.last_activity = datetime.now(EASTERN)
        text = re.sub(r"\x1b\[[0-9;]*m", "", msg.message.decode("utf8", "backslashreplace")).rstrip()
        if not text:
            return
        ts = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S")
        with open(self._get_log_file(), "a") as f:
            f.write(f"[{ts}] {text}\n")

    # State callback
    def _state_callback(self, state):
        self.last_activity = datetime.now(EASTERN)
        entity_id = state.key
        friendly = self.entity_map.get(entity_id, "unknown")
        value = getattr(state, "state", None)

        # Skip if the value is None or nan
        if value is None:
            return

        # Check if value is a number and if it's NaN
        try:
            if isinstance(value, (int, float)) and isnan(value):
                return
        except (TypeError, ValueError):
            pass

        # Write to the CSV file
        now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S")
        with open(self._get_csv_file(), "a", newline="") as f:
            csv.writer(f).writerow([now, entity_id, friendly, value])

        # Write to InfluxDB
        if self._influx_write_api is not None:
            try:
                try:
                    influx_value: float | str = float(value)
                    field_key = "value"
                except (TypeError, ValueError):
                    influx_value = str(value)
                    field_key = "value_str"

                point = (
                    Point("sensor_state")
                    .tag("host", self.host)
                    .tag("entity_id", str(entity_id))
                    .tag("friendly_name", friendly)
                    .field(field_key, influx_value)
                    .time(datetime.now(EASTERN))
                )
                self._influx_write_api.write(bucket=self._influx_bucket, org=self._influx_org, record=point)
            except Exception as e:
                log(f"WARNING: InfluxDB write failed for {self.host}/{friendly}: {e}")

    # Delete log files older than retention_days
    def _delete_old_logs(self):
        retention_days = self.retention_days
        if retention_days is None:
            return
        cutoff = datetime.now(EASTERN).date() - timedelta(days=retention_days)
        for pattern in ["esphome_*.csv", "esphome_*.log"]:
            for old_file in glob.glob(os.path.join(self.csv_dir, pattern)):
                filename = os.path.basename(old_file)
                try:
                    date_str = filename.split("_", 1)[1].rsplit(".", 1)[0]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if file_date < cutoff:
                        os.remove(old_file)
                        log(f"Deleted old file: {old_file}")
                except (ValueError, IndexError):
                    continue

    # Close InfluxDB client
    def close(self):
        if self._influx_write_api is not None:
            try:
                self._influx_write_api.close()
            except Exception:
                pass
        if self._influx_client is not None:
            try:
                self._influx_client.close()
            except Exception:
                pass

    # Run the logger with retry logic
    async def run(self):
        try:
            while True:
                try:
                    if not self.connected:
                        log(f"Connecting to {self.host}")
                        await self.connect()

                    # Keep the connection alive
                    await asyncio.sleep(10)

                    # Assume disconnected if no activity for more than 5 minutes
                    last_activity = self.last_activity
                    if last_activity and datetime.now(EASTERN) - last_activity > timedelta(minutes=5):
                        log(f"No activity from {self.host} for 5 minutes, reconnecting")
                        self.connected = False
                        self.last_activity = None
                        try:
                            await self.client.disconnect()
                        except Exception:
                            pass

                except APIConnectionError as e:
                    log(f"Connection lost to {self.host}: {e}")
                    self.connected = False
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    log(f"Retrying connection to {self.host} in {self.retry_interval} seconds...")
                    await asyncio.sleep(self.retry_interval)

                except Exception as e:
                    log(f"Unexpected error with {self.host}: {e}")
                    self.connected = False
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    log(f"Retrying connection to {self.host} in {self.retry_interval} seconds...")
                    await asyncio.sleep(self.retry_interval)
        finally:
            self.close()
