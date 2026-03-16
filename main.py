import asyncio
from esphome_logger import ESPHomeLogger
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
# Sewage Tank
API_HOST_SEWAGE_TANK=os.getenv("API_HOST_SEWAGE_TANK")
API_SEWAGE_TANK_PASSWORD=os.getenv("API_SEWAGE_TANK_PASSWORD")

# Log retention (days) - set to None to keep all logs
LOG_RETENTION_DAYS = os.getenv("LOG_RETENTION_DAYS")
if LOG_RETENTION_DAYS is not None:
    LOG_RETENTION_DAYS = int(LOG_RETENTION_DAYS)

async def main():
    devices = [
        {"host": API_HOST_SEWAGE_TANK, "password": API_SEWAGE_TANK_PASSWORD, "csv_dir": "logs/sewage-tank", "retention_days": LOG_RETENTION_DAYS},
    ]
    loggers = [ESPHomeLogger(**dev) for dev in devices]
    await asyncio.gather(*(logger.run() for logger in loggers))

if __name__ == "__main__":
    asyncio.run(main())