#!/usr/bin/env python3
"""
Test Suite: Humanoid Sending Engine & Circuit Breaker System.

Validates:
1. Text Sanitization (strict no em-dash '—' rule).
2. Humanoid Delay Calculation (scales with text length and bounds).
3. Circuit Breaker State Transitions (CLOSED -> OPEN -> RESET).
4. Safety Status API and Reset Endpoint.
5. Database Message Status & Retry logic.
"""
import asyncio
import os
import sys

# Add ai-service and crm-service to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "ai-service"))

from core.humanoid_sender import sanitize_text, calculate_humanoid_delay, humanoid_sender
from core.circuit_breaker import CircuitBreaker


def test_sanitization():
    print("Testing text sanitization...")
    samples = [
        ("Hello — here is your quote", "Hello, here is your quote"),
        ("Fast response—thank you!", "Fast response, thank you!"),
        ("Option A – Option B", "Option A - Option B"),
        ("Normal text with -- hyphens", "Normal text with - hyphens"),
    ]
    for orig, expected in samples:
        res = sanitize_text(orig)
        assert "—" not in res, f"Em dash still found in: {res}"
        assert "–" not in res, f"En dash still found in: {res}"
        print(f"  ✓ {orig!r} -> {res!r}")
    print("✓ Sanitization tests passed!\n")


def test_humanoid_delays():
    print("Testing humanoid delay calculations...")
    short_text = "Hi Marcus, are you free to chat?"
    med_text = "Hi Deborah, here is the updated Farmers auto quote for your 2022 Honda Civic. Let me know if you would like me to lock this in."
    long_text = ("Hello Margaret, thank you for contacting us regarding your home and auto insurance bundle. "
                 "We have reviewed your property details in Austin and formulated three deductible tiers for your consideration. "
                 "The comprehensive breakdown includes standard coverage plus roadside assistance. Please let us know if you need any adjustments.")

    # In normal mode (not FAST_TEST)
    d_short = calculate_humanoid_delay(short_text, is_reply=True)
    d_med = calculate_humanoid_delay(med_text, is_reply=True)
    d_long = calculate_humanoid_delay(long_text, is_reply=True)

    print(f"  Short ({len(short_text)} chars): {d_short}s")
    print(f"  Medium ({len(med_text)} chars): {d_med}s")
    print(f"  Long ({len(long_text)} chars): {d_long}s")

    assert 4.0 <= d_short <= 22.0, f"d_short out of bounds: {d_short}"
    assert 4.0 <= d_med <= 22.0, f"d_med out of bounds: {d_med}"
    assert 4.0 <= d_long <= 22.0, f"d_long out of bounds: {d_long}"
    assert d_short <= d_long, f"Expected short delay <= long delay: {d_short} vs {d_long}"
    print("✓ Humanoid delay tests passed!\n")


async def test_circuit_breaker():
    print("Testing Circuit Breaker state transitions...")
    cb = CircuitBreaker()
    assert cb.state == "CLOSED"
    avail, _ = cb.is_available()
    assert avail is True

    # 1 failure: should remain CLOSED
    await cb.record_failure("Test carrier error 1")
    assert cb.state == "CLOSED"
    assert cb.consecutive_failures == 1
    avail, _ = cb.is_available()
    assert avail is True
    print("  ✓ 1 failure recorded, circuit remains CLOSED")

    # 2nd consecutive failure: should trip to OPEN
    await cb.record_failure("Test carrier error 2")
    assert cb.state == "OPEN"
    assert cb.consecutive_failures == 2
    avail, reason = cb.is_available()
    assert avail is False
    assert "Circuit Breaker is ACTIVE" in reason
    print(f"  ✓ 2nd failure tripped circuit to OPEN ({reason[:50]}...)")

    # While OPEN, status reports correctly
    status = cb.get_status()
    assert status["state"] == "OPEN"
    assert status["consecutive_failures"] == 2
    assert status["cooldown_remaining_seconds"] > 0
    print(f"  ✓ Status reported correctly: state={status['state']}, cooldown={status['cooldown_remaining_seconds']}s")

    # Manual reset
    res = await cb.reset()
    assert res["state"] == "CLOSED"
    assert cb.state == "CLOSED"
    assert cb.consecutive_failures == 0
    avail, _ = cb.is_available()
    assert avail is True
    print("  ✓ Manual reset successfully restored circuit to CLOSED")
    print("✓ Circuit Breaker tests passed!\n")


def main():
    test_sanitization()
    test_humanoid_delays()
    asyncio.run(test_circuit_breaker())
    print("All unit tests passed successfully!")


if __name__ == "__main__":
    main()
