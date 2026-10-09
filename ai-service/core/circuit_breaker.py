"""
Circuit Breaker System - protects Apple ID from permanent bans and manages send failures.

When an Apple ID encounters delivery failures (e.g. Apple throttling, carrier rejects,
or AppleScript communication issues), repeated automated hammering guarantees an
account suspension.

This module acts as an automated safety breaker:
1. Tracks consecutive delivery failures.
2. If 2 consecutive failures occur (or a fatal account block error is detected),
   the circuit trips to OPEN.
3. While OPEN, all outbound sends via Apple/BlueBubbles are frozen immediately.
4. Broadcasts an activity feed alert to the admin CRM.
5. After a safety cooldown (default 30 mins) or manual admin unpause, transitions
   to HALF_OPEN / CLOSED to safely resume sending.
"""
import asyncio
import logging
import os
import time
from typing import Optional

from core.activity_events import emit_activity_event
from core.config import DEFAULT_BUSINESS_ID

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_THRESHOLD", "2"))
COOLDOWN_SECONDS = float(os.environ.get("CIRCUIT_BREAKER_COOLDOWN", "1800.0"))  # 30 minutes


class CircuitBreaker:
    def __init__(self):
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.consecutive_failures: int = 0
        self.last_failure_time: float = 0.0
        self.tripped_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self._lock = asyncio.Lock()

    def is_available(self) -> tuple[bool, str]:
        """
        Checks whether outbound iMessage sending is currently allowed.
        Returns (is_allowed, reason).
        """
        now = time.time()
        if self.state == "OPEN":
            if self.tripped_at and (now - self.tripped_at >= COOLDOWN_SECONDS):
                logger.info("[circuit_breaker] Cooldown period expired. Transitioning to HALF_OPEN trial mode.")
                self.state = "HALF_OPEN"
                return True, "Trial mode (HALF_OPEN)"
            
            elapsed = int(now - (self.tripped_at or now))
            remaining_mins = max(1, int((COOLDOWN_SECONDS - elapsed) / 60))
            return False, f"Safety Circuit Breaker is ACTIVE. Outbound sends are paused to protect your Apple account. Cooldown: ~{remaining_mins}m or click Resume in CRM."

        return True, "Circuit closed (healthy)"

    async def record_success(self):
        """Called upon successful send. Resets failure counters."""
        async with self._lock:
            if self.state in ("OPEN", "HALF_OPEN"):
                logger.info(f"[circuit_breaker] Successful send confirmed! Resetting circuit from {self.state} to CLOSED.")
                asyncio.create_task(
                    emit_activity_event(
                        DEFAULT_BUSINESS_ID,
                        "circuit_breaker_recovered",
                        "Outbound iMessage Resumed: Delivery successful, safety circuit closed.",
                        metadata={"state": "CLOSED"}
                    )
                )
            self.state = "CLOSED"
            self.consecutive_failures = 0
            self.last_error = None
            self.tripped_at = None

    async def record_failure(self, error_message: str):
        """
        Called when a send fails. Increments failure counter and trips
        if threshold is breached.
        """
        async with self._lock:
            now = time.time()
            self.last_error = error_message
            self.last_failure_time = now
            self.consecutive_failures += 1

            logger.warning(
                f"[circuit_breaker] Send failure recorded (#{self.consecutive_failures}/{FAILURE_THRESHOLD}): {error_message}"
            )

            # Check if this error is an immediate fatal indicator (Apple ID ban/lock)
            is_fatal_apple_block = any(
                keyword in (error_message or "").lower()
                for keyword in ("account locked", "apple id blocked", "apple id restricted", "account disabled", "identity blocked")
            )

            if self.consecutive_failures >= FAILURE_THRESHOLD or is_fatal_apple_block:
                self.state = "OPEN"
                self.tripped_at = now
                logger.error(
                    f"[circuit_breaker] CIRCUIT BREAKER TRIPPED to OPEN! Outbound iMessage paused to protect Apple ID. "
                    f"Reason: {error_message}"
                )
                # Emit high-priority alert to the activity feed
                asyncio.create_task(
                    emit_activity_event(
                        DEFAULT_BUSINESS_ID,
                        "circuit_breaker_tripped",
                        f"Outbound iMessage Paused: Circuit Breaker activated after delivery failure to protect your Apple account.",
                        metadata={
                            "reason": error_message,
                            "consecutive_failures": self.consecutive_failures,
                            "tripped_at": now,
                            "cooldown_seconds": COOLDOWN_SECONDS
                        }
                    )
                )

    async def reset(self) -> dict:
        """Manual admin reset to unpause sending."""
        async with self._lock:
            prev_state = self.state
            self.state = "CLOSED"
            self.consecutive_failures = 0
            self.last_error = None
            self.tripped_at = None
            logger.info(f"[circuit_breaker] Manual reset executed by admin. Circuit transitioned from {prev_state} to CLOSED.")
            asyncio.create_task(
                emit_activity_event(
                    DEFAULT_BUSINESS_ID,
                    "circuit_breaker_reset",
                    "Outbound iMessage Circuit Breaker manually reset by admin. Normal sending resumed.",
                    metadata={"previous_state": prev_state}
                )
            )
            return {"success": True, "state": "CLOSED"}

    def get_status(self) -> dict:
        """Returns current safety and circuit breaker metrics."""
        now = time.time()
        cooldown_remaining = 0
        if self.state == "OPEN" and self.tripped_at:
            cooldown_remaining = max(0, int(self.tripped_at + COOLDOWN_SECONDS - now))

        from core.humanoid_sender import humanoid_sender, HOURLY_OUTBOUND_LIMIT, DAILY_OUTBOUND_LIMIT

        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": FAILURE_THRESHOLD,
            "last_error": self.last_error,
            "tripped_at": self.tripped_at,
            "cooldown_remaining_seconds": cooldown_remaining,
            "hourly_sent_count": humanoid_sender.get_hourly_count(),
            "hourly_limit": HOURLY_OUTBOUND_LIMIT,
            "daily_sent_count": humanoid_sender.get_daily_count(),
            "daily_limit": DAILY_OUTBOUND_LIMIT,
            "humanoid_pacing_active": True
        }


# Process-wide singleton
circuit_breaker = CircuitBreaker()
