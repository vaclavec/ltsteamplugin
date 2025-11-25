"""Bandwidth throttling and rate limiting for LuaTools downloads."""

from __future__ import annotations

import threading
import time
from typing import Optional

from logger import logger

# Global throttle state
_THROTTLE_STATE = {
    "enabled": False,
    "max_bytes_per_second": 0,  # 0 = unlimited
    "current_speed": 0.0,
    "lock": threading.Lock(),
}


def enable_throttling(max_bytes_per_second: int = 1024 * 1024) -> None:
    """Enable bandwidth throttling."""
    with _THROTTLE_STATE["lock"]:
        _THROTTLE_STATE["enabled"] = True
        _THROTTLE_STATE["max_bytes_per_second"] = max(max_bytes_per_second, 1024)  # Minimum 1 KB/s
        logger.log(f"LuaTools: Bandwidth throttling enabled at {max_bytes_per_second} bytes/sec")


def disable_throttling() -> None:
    """Disable bandwidth throttling."""
    with _THROTTLE_STATE["lock"]:
        _THROTTLE_STATE["enabled"] = False
        logger.log("LuaTools: Bandwidth throttling disabled")


def set_bandwidth_limit(max_bytes_per_second: int) -> None:
    """Set bandwidth limit."""
    with _THROTTLE_STATE["lock"]:
        _THROTTLE_STATE["max_bytes_per_second"] = max(max_bytes_per_second, 1024)
        if _THROTTLE_STATE["enabled"]:
            logger.log(f"LuaTools: Bandwidth limit set to {max_bytes_per_second} bytes/sec")


def get_bandwidth_settings() -> dict:
    """Get current bandwidth settings."""
    with _THROTTLE_STATE["lock"]:
        return {
            "enabled": _THROTTLE_STATE["enabled"],
            "max_bytes_per_second": _THROTTLE_STATE["max_bytes_per_second"],
            "current_speed": _THROTTLE_STATE["current_speed"],
        }


class BandwidthLimiter:
    """Context manager for bandwidth-limited downloads."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.bytes_downloaded = 0

    def throttle_if_needed(self, bytes_chunk: int) -> None:
        """Throttle download if bandwidth limit is set."""
        with _THROTTLE_STATE["lock"]:
            if not _THROTTLE_STATE["enabled"]:
                return

            max_bytes_per_sec = _THROTTLE_STATE["max_bytes_per_second"]
            if max_bytes_per_sec <= 0:
                return

        if self.start_time is None:
            self.start_time = time.time()

        self.bytes_downloaded += bytes_chunk
        elapsed = time.time() - self.start_time

        # Calculate expected time for downloaded bytes
        expected_time = self.bytes_downloaded / max_bytes_per_sec

        if expected_time > elapsed:
            # Sleep to maintain the rate limit
            sleep_time = expected_time - elapsed
            time.sleep(sleep_time)

        # Update current speed
        if elapsed > 0:
            with _THROTTLE_STATE["lock"]:
                _THROTTLE_STATE["current_speed"] = self.bytes_downloaded / elapsed

    def reset(self) -> None:
        """Reset the limiter."""
        self.start_time = None
        self.bytes_downloaded = 0


def format_bandwidth(bytes_per_second: float) -> str:
    """Format bandwidth as human-readable string."""
    if bytes_per_second < 1024:
        return f"{bytes_per_second:.0f} B/s"
    elif bytes_per_second < 1024 * 1024:
        return f"{bytes_per_second / 1024:.1f} KB/s"
    elif bytes_per_second < 1024 * 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bytes_per_second / (1024 * 1024 * 1024):.1f} GB/s"


def format_time_remaining(bytes_remaining: int, current_speed: float) -> str:
    """Format estimated time remaining."""
    if current_speed <= 0:
        return "Unknown"

    seconds_remaining = bytes_remaining / current_speed

    if seconds_remaining < 60:
        return f"{int(seconds_remaining)}s"
    elif seconds_remaining < 3600:
        minutes = int(seconds_remaining / 60)
        seconds = int(seconds_remaining % 60)
        return f"{minutes}m {seconds}s"
    else:
        hours = int(seconds_remaining / 3600)
        minutes = int((seconds_remaining % 3600) / 60)
        return f"{hours}h {minutes}m"
