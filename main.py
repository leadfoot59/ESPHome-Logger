import asyncio
from esphome_logger import ESPHomeLogger
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
# Sewage Tank
API_HOST_SEWAGE_TANK=os.getenv("API_HOST_SEWAGE_TANK")
API_SEWAGE_TANK_PASSWORD=os.getenv("API_SEWAGE_TANK_PASSWORD")

async def main():
    devices = [
        {"host": API_HOST_SEWAGE_TANK, "password": API_SEWAGE_TANK_PASSWORD, "csv_dir": "logs/sewage-tank"},
    ]
    loggers = [ESPHomeLogger(**dev) for dev in devices]
    await asyncio.gather(*(logger.run() for logger in loggers))

if __name__ == "__main__":
    asyncio.run(main())