"""
Standalone follow-up scheduler — run separately from the web server.
  python scheduler.py
Railway: add as a second service pointing to this file.
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from main import _send_pending_follow_ups

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INTERVAL_HOURS = 6


async def run():
    logger.info("[scheduler] Started — running every %s hours", INTERVAL_HOURS)
    while True:
        try:
            await _send_pending_follow_ups()
        except Exception as e:
            logger.error("[scheduler] Error: %s", e)
        await asyncio.sleep(INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    asyncio.run(run())
