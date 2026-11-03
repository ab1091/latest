"""
Humanoid Sending Engine - simulates human messaging behavior for Apple iMessage / SMS.

Apple anti-abuse heuristics actively flag and ban accounts exhibiting bot-like
patterns:
1. Deterministic or zero-delay sending right after an inbound message or trigger.
2. Unnatural burst frequency (e.g. rigid 8-second intervals).
3. Instant paragraph delivery without typing duration.
4. Sending high volumes of cold messages in a short rolling window.

This module provides:
- Reading and typing simulation based on character length and human WPM.
- Natural Gaussian jitter and micro-pauses.
- Randomized inter-message cadence spacing (20-45 seconds).
- Hourly velocity throttling (max 20 messages/rolling hour).
- Content sanitization to strictly prevent em dashes.
"""
import asyncio
import logging
import os
import random
import re
import time
from typing import List

logger = logging.getLogger(__name__)

# Configurable velocity limits
DAILY_OUTBOUND_LIMIT = int(os.environ.get("HUMANOID_DAILY_LIMIT", "50"))
HOURLY_OUTBOUND_LIMIT = int(os.environ.get("HUMANOID_HOURLY_LIMIT", "20"))
MIN_GAP_SECONDS = float(os.environ.get("HUMANOID_MIN_GAP_SECONDS", "20.0"))
MAX_GAP_SECONDS = float(os.environ.get("HUMANOID_MAX_GAP_SECONDS", "45.0"))


def sanitize_text(text: str) -> str:
    """
    Sanitize text to guarantee natural human phrasing and strictly eliminate
    em dashes and en dashes, replacing them with commas, periods,
    or hyphens as appropriate.
    """

    if not text:
        return text
    # Replace em-dash surrounded by spaces with comma or hyphen
    cleaned = re.sub(r"\s*—\s*", ", ", text)
    # Replace any leftover em-dash or en-dash
    cleaned = cleaned.replace("—", "-").replace("–", "-")
    # Replace double hyphens
    cleaned = re.sub(r"--+", "-", cleaned)
    # Clean up double commas or awkward punctuation
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    return cleaned.strip()


def calculate_humanoid_delay(text: str, is_reply: bool = True) -> float:
    """
    Calculates realistic human delay (reading time + typing duration + jitter).
    - Human reading speed: ~200-250 wpm. For inbound context or formulation: 2.5 - 5.0s.
    - Human mobile typing speed: 38 - 52 words per minute (~190 - 260 chars per minute).
      That equates to roughly 0.025 to 0.038 seconds per character.
    - Adds natural jitter (± 20%) and micro-pauses (1-2s).
    - Returns seconds bounded between 4.0s and 22.0s.
    """
    char_count = len(text or "")
    if char_count == 0:
        return 3.0

    # In test mode or when running scripts with FAST_TEST=1, speed up
    if os.environ.get("FAST_TEST") == "1":
        return 0.1

    # 1. Reading / formulation delay
    reading_delay = random.uniform(2.5, 4.5) if is_reply else random.uniform(1.8, 3.2)

    # 2. Typing speed: ~28-36 milliseconds per character with random variance
    char_speed = random.uniform(0.028, 0.038)
    typing_delay = char_count * char_speed

    # 3. Natural micro-pauses (simulating hesitations / corrections)
    micro_pauses = 0.0
    if char_count > 60:
        micro_pauses += random.uniform(1.0, 2.5)
    if char_count > 150:
        micro_pauses += random.uniform(1.2, 3.0)

    # 4. Human Gaussian jitter (± 15%)
    jitter_factor = random.gauss(1.0, 0.15)
    total = (reading_delay + typing_delay + micro_pauses) * jitter_factor

    # Safe boundaries: at least 4.0s for short texts, capped at 22.0s so it doesn't hang forever
    clamped = max(4.0, min(22.0, total))
    return round(clamped, 2)


class HumanoidSender:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._last_send_time = 0.0
        self._hourly_timestamps: List[float] = []
        self._daily_timestamps: List[float] = []

    def _get_daily_count_db(self) -> int:
        """Fetch today's sent count from the messages table as source of truth."""
        try:
            from core.db import get_conn
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM messages WHERE role = 'agent' AND created_at >= CURRENT_DATE;"
                )
                cnt = cur.fetchone()[0]
            conn.close()
            return cnt
        except Exception as e:
            logger.warning(f"[humanoid_sender] DB daily count lookup error: {e}")
            from datetime import datetime
            midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            self._daily_timestamps = [t for t in self._daily_timestamps if t >= midnight]
            return len(self._daily_timestamps)

    def check_velocity_limit(self) -> tuple[bool, str]:
        """
        Ensures we do not exceed the safe hourly (20/hr) and daily (50/day) outbound velocity
        to strictly protect the Apple ID from spam heuristics.
        """
        # 1. Check daily limit (strictly max 50/day)
        daily_count = self._get_daily_count_db()
        if daily_count >= DAILY_OUTBOUND_LIMIT:
            return False, f"Daily limit reached ({daily_count}/{DAILY_OUTBOUND_LIMIT} sent today). Pausing until tomorrow to protect Apple ID."

        # 2. Check hourly limit (max 20/hr)
        now = time.time()
        one_hour_ago = now - 3600.0
        self._hourly_timestamps = [t for t in self._hourly_timestamps if t > one_hour_ago]

        if len(self._hourly_timestamps) >= HOURLY_OUTBOUND_LIMIT:
            oldest = self._hourly_timestamps[0]
            minutes_left = max(1, int((oldest + 3600.0 - now) / 60))
            return False, f"Hourly limit reached ({len(self._hourly_timestamps)}/{HOURLY_OUTBOUND_LIMIT} sent in past hour). Cooldown: ~{minutes_left}m to protect Apple ID."

        return True, ""

    def record_outbound_send(self):
        """Records an outbound send timestamp for velocity pacing."""
        now = time.time()
        self._hourly_timestamps.append(now)
        self._daily_timestamps.append(now)
        self._last_send_time = now

    def get_hourly_count(self) -> int:
        now = time.time()
        one_hour_ago = now - 3600.0
        self._hourly_timestamps = [t for t in self._hourly_timestamps if t > one_hour_ago]
        return len(self._hourly_timestamps)

    def get_daily_count(self) -> int:
        return self._get_daily_count_db()

    async def wait_inter_message_gap(self):
        """
        Enforces a randomized, human cadence gap between outbound sends.
        Real humans do not send at fixed 8.0s intervals; they send with natural
        spacing (e.g. 20-45s) between messages.
        """
        if os.environ.get("FAST_TEST") == "1":
            return

        if self._last_send_time <= 0:
            return

        now = time.time()
        elapsed = now - self._last_send_time

        # Target a randomized interval between MIN_GAP_SECONDS and MAX_GAP_SECONDS
        target_interval = random.uniform(MIN_GAP_SECONDS, MAX_GAP_SECONDS)
        wait_needed = target_interval - elapsed

        if wait_needed > 0:
            wait_needed = min(MAX_GAP_SECONDS, wait_needed)
            logger.info(
                f"[humanoid:pacing] Waiting {wait_needed:.1f}s to maintain human cadence "
                f"(target interval: {target_interval:.1f}s, elapsed: {elapsed:.1f}s)"
            )
            await asyncio.sleep(wait_needed)

    async def simulate_typing(self, text: str, is_reply: bool = True):
        """Simulates human typing and formulation time."""
        delay = calculate_humanoid_delay(text, is_reply=is_reply)
        logger.info(f"[humanoid:typing] Simulating {delay:.1f}s typing delay for {len(text)} chars: {text[:40]!r}...")
        await asyncio.sleep(delay)


# Process-wide singleton
humanoid_sender = HumanoidSender()
