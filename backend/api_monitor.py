"""API monitoring and analytics for LuaTools."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from logger import logger
from paths import backend_path
from utils import read_json, write_json

API_MONITOR_FILE = "api_monitor.json"
MONITOR_LOCK = threading.Lock()

# In-memory cache
_MONITOR_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False
_MAX_HISTORY_PER_API = 1000


def _get_monitor_path() -> str:
    return backend_path(API_MONITOR_FILE)


def _ensure_monitor_initialized() -> None:
    """Initialize API monitoring file if not exists."""
    global _MONITOR_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _MONITOR_CACHE:
        return

    path = _get_monitor_path()
    if os.path.exists(path):
        try:
            _MONITOR_CACHE = read_json(path)
            _CACHE_INITIALIZED = True
            return
        except Exception as exc:
            logger.warn(f"LuaTools: Failed to load API monitor: {exc}")

    # Create default structure
    _MONITOR_CACHE = {
        "version": 1,
        "created_at": time.time(),
        "apis": {},  # url: {requests: [], last_status: 200, up_count: 0, down_count: 0}
    }
    _persist_monitor()
    _CACHE_INITIALIZED = True


def _persist_monitor() -> None:
    """Write monitor data to disk."""
    try:
        path = _get_monitor_path()
        write_json(path, _MONITOR_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist API monitor: {exc}")


def record_api_request(api_url: str, status_code: int = 200, response_time_ms: float = 0.0, success: bool = True) -> None:
    """Record an API request."""
    with MONITOR_LOCK:
        _ensure_monitor_initialized()

        api_url_str = str(api_url).strip()
        if api_url_str not in _MONITOR_CACHE["apis"]:
            _MONITOR_CACHE["apis"][api_url_str] = {
                "requests": [],
                "last_status": 0,
                "last_checked": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_response_time": 0.0,
            }

        api_entry = _MONITOR_CACHE["apis"][api_url_str]
        request_entry = {
            "timestamp": time.time(),
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "success": success,
        }

        api_entry["requests"].append(request_entry)
        api_entry["last_status"] = status_code
        api_entry["last_checked"] = time.time()
        api_entry["total_response_time"] = api_entry.get("total_response_time", 0.0) + response_time_ms

        if success:
            api_entry["success_count"] = api_entry.get("success_count", 0) + 1
        else:
            api_entry["failure_count"] = api_entry.get("failure_count", 0) + 1

        # Keep history manageable
        if len(api_entry["requests"]) > _MAX_HISTORY_PER_API:
            api_entry["requests"] = api_entry["requests"][-_MAX_HISTORY_PER_API :]

        _persist_monitor()


def get_api_status(api_url: str) -> Dict[str, Any]:
    """Get current status of an API."""
    with MONITOR_LOCK:
        _ensure_monitor_initialized()

        api_url_str = str(api_url).strip()
        if api_url_str not in _MONITOR_CACHE["apis"]:
            return {
                "url": api_url_str,
                "status": "unknown",
                "last_checked": 0,
                "uptime_percentage": 0,
                "average_response_time_ms": 0,
            }

        api_entry = _MONITOR_CACHE["apis"][api_url_str]
        requests = api_entry.get("requests", [])
        total = len(requests)

        uptime = 0
        avg_response_time = 0
        if total > 0:
            success = api_entry.get("success_count", 0)
            uptime = (success / total * 100) if total > 0 else 0
            total_time = api_entry.get("total_response_time", 0.0)
            avg_response_time = total_time / total if total > 0 else 0

        is_up = api_entry.get("last_status", 0) == 200
        return {
            "url": api_url_str,
            "status": "up" if is_up else "down",
            "last_checked": api_entry.get("last_checked", 0),
            "last_status_code": api_entry.get("last_status", 0),
            "uptime_percentage": round(uptime, 2),
            "average_response_time_ms": round(avg_response_time, 2),
            "total_requests": total,
            "success_count": api_entry.get("success_count", 0),
            "failure_count": api_entry.get("failure_count", 0),
        }


def get_all_api_statuses() -> List[Dict[str, Any]]:
    """Get status of all monitored APIs."""
    with MONITOR_LOCK:
        _ensure_monitor_initialized()

        statuses = []
        for api_url in _MONITOR_CACHE["apis"]:
            status = get_api_status(api_url)
            statuses.append(status)

        return sorted(statuses, key=lambda x: x.get("last_checked", 0), reverse=True)


def get_api_performance_metrics(api_url: str, limit: int = 100) -> Dict[str, Any]:
    """Get detailed performance metrics for an API."""
    with MONITOR_LOCK:
        _ensure_monitor_initialized()

        api_url_str = str(api_url).strip()
        if api_url_str not in _MONITOR_CACHE["apis"]:
            return {"success": False, "error": "API not found"}

        api_entry = _MONITOR_CACHE["apis"][api_url_str]
        requests = api_entry.get("requests", [])[-limit :]

        response_times = [r.get("response_time_ms", 0) for r in requests]
        status_codes = [r.get("status_code", 0) for r in requests]

        return {
            "success": True,
            "url": api_url_str,
            "request_count": len(requests),
            "latest_requests": requests,
            "min_response_time_ms": min(response_times) if response_times else 0,
            "max_response_time_ms": max(response_times) if response_times else 0,
            "avg_response_time_ms": sum(response_times) / len(response_times) if response_times else 0,
            "status_code_distribution": _count_status_codes(status_codes),
        }


def _count_status_codes(codes: List[int]) -> Dict[int, int]:
    """Count occurrences of each status code."""
    counts: Dict[int, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return counts


def get_monitor_json() -> str:
    """Get all monitoring data as JSON."""
    statuses = get_all_api_statuses()
    return json.dumps({
        "success": True,
        "apis": statuses,
        "timestamp": time.time(),
    })


def is_api_available(api_url: str, required_uptime_percentage: float = 80.0) -> bool:
    """Check if an API is available based on uptime threshold."""
    status = get_api_status(api_url)
    return status.get("uptime_percentage", 0) >= required_uptime_percentage
