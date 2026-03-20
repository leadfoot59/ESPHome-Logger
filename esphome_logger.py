import asyncio
import csv
import glob
from math import isnan
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aioesphomeapi import APIClient
from aioesphomeapi.core import APIConnectionError

EASTERN = ZoneInfo("America/New_York")

# ESPHomeLogger class
class ESPHomeLogger:
    def __init__(self, host, password=None, csv_dir="logs", retry_interval=15, retention_days=None):
        self.host = host
        self.client = APIClient(host, 6053, password=password, noise_psk=password)
        self.csv_dir = csv_dir
        self.current_date = None
        self.entity_map = {}
        self.retry_interval = retry_interval
        self.retention_days = retention_days
        self.connected = False
        self.connected_time = None

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
            self.connected = True
            self.connected_time = datetime.now(EASTERN)
            print(f"Successfully connected to {self.host}")
        except APIConnectionError as e:
            self.connected = False
            print(f"Connection failed to {self.host}: {e}")
            raise
        except Exception as e:
            self.connected = False
            print(f"Unexpected error connecting to {self.host}: {e}")
            raise

    # State callback
    def _state_callback(self, state):
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
            # If it's not a number, continue processing
            pass

        # Write to the CSV file
        now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S")
        with open(self._get_csv_file(), "a", newline="") as f:
            csv.writer(f).writerow([now, entity_id, friendly, value])
            # print(f"State update: {now} - {self.host} - {entity_id} - {friendly} - {value}")

    # Delete log files older than retention_days
    def _delete_old_logs(self):
        if self.retention_days is None:
            return
        cutoff = datetime.now(EASTERN).date() - timedelta(days=self.retention_days)
        for csv_file in glob.glob(os.path.join(self.csv_dir, "esphome_*.csv")):
            filename = os.path.basename(csv_file)
            try:
                date_str = filename.replace("esphome_", "").replace(".csv", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if file_date < cutoff:
                    os.remove(csv_file)
                    print(f"Deleted old log file: {csv_file}")
            except ValueError:
                continue

    # Run the logger with retry logic
    async def run(self):
        while True:
            try:
                if not self.connected:
                    print(f"Connecting to {self.host}")
                    await self.connect()
                
                # Keep the connection alive
                await asyncio.sleep(10)
                
                # Assume disconnected if connected time is more than 5 minute ago
                if self.connected_time and datetime.now(EASTERN) - self.connected_time > timedelta(minutes=5):
                    print(f"Last connection was more than 5 minutes ago, assuming disconnected")
                    self.connected = False
                    self.connected_time = None

            except APIConnectionError as e:
                print(f"Connection lost to {self.host}: {e}")
                self.connected = False
                print(f"Retrying connection to {self.host} in {self.retry_interval} seconds...")
                await asyncio.sleep(self.retry_interval)
                
            except Exception as e:
                print(f"Unexpected error with {self.host}: {e}")
                self.connected = False
                print(f"Retrying connection to {self.host} in {self.retry_interval} seconds...")
                await asyncio.sleep(self.retry_interval)