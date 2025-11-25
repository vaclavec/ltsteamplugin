"""Download history tracking for LuaTools."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from logger import logger
from paths import backend_path
from utils import read_json, write_json

DOWNLOAD_HISTORY_FILE = "download_history.json"
HISTORY_LOCK = threading.Lock()

# In-memory cache
_HISTORY_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False
_MAX_HISTORY_ENTRIES = 1000  # Keep last 1000 downloads


def _get_history_path() -> str:
    return backend_path(DOWNLOAD_HISTORY_FILE)


def _ensure_history_initialized() -> None:
    """Initialize history file if not exists."""
    global _HISTORY_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _HISTORY_CACHE:
        return

    path = _get_history_path()
    if os.path.exists(path):
        try:
            _HISTORY_CACHE = read_json(path)
            _CACHE_INITIALIZED = True
            return
        except Exception as exc:
            logger.warn(f"LuaTools: Failed to load download history: {exc}")

    # Create default history structure
    _HISTORY_CACHE = {
        "version": 1,
        "created_at": time.time(),
        "downloads": [],  # List of download entries
        "total_downloaded_bytes": 0,
    }
    _persist_history()
    _CACHE_INITIALIZED = True


def _persist_history() -> None:
    """Write history to disk."""
    try:
        path = _get_history_path()
        write_json(path, _HISTORY_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist download history: {exc}")


def record_download_start(download_id: str, appid: int, app_name: str, file_url: str, file_size: int = 0) -> None:
    """Record the start of a download."""
    with HISTORY_LOCK:
        _ensure_history_initialized()

        entry = {
            "id": download_id,
            "appid": appid,
            "app_name": app_name,
            "file_url": file_url,
            "file_size": file_size,
            "started_at": time.time(),
            "status": "downloading",
        }

        _HISTORY_CACHE["downloads"].append(entry)

        # Keep history size manageable
        if len(_HISTORY_CACHE["downloads"]) > _MAX_HISTORY_ENTRIES:
            _HISTORY_CACHE["downloads"] = _HISTORY_CACHE["downloads"][-_MAX_HISTORY_ENTRIES :]

        _persist_history()
        logger.log(f"LuaTools: Started tracking download {download_id} for appid {appid}")


def record_download_complete(download_id: str, success: bool = True, bytes_downloaded: int = 0, error: str = "") -> None:
    """Record the completion of a download."""
    with HISTORY_LOCK:
        _ensure_history_initialized()

        # Find and update entry
        for entry in _HISTORY_CACHE["downloads"]:
            if entry.get("id") == download_id:
                entry["completed_at"] = time.time()
                entry["status"] = "success" if success else "failed"
                entry["bytes_downloaded"] = bytes_downloaded
                if error:
                    entry["error"] = error

                if success:
                    _HISTORY_CACHE["total_downloaded_bytes"] = _HISTORY_CACHE.get("total_downloaded_bytes", 0) + bytes_downloaded

                _persist_history()
                logger.log(f"LuaTools: Download {download_id} completed with status {'success' if success else 'failed'}")
                return

        logger.warn(f"LuaTools: Download entry {download_id} not found for completion record")


def record_download_cancelled(download_id: str) -> None:
    """Record that a download was cancelled."""
    with HISTORY_LOCK:
        _ensure_history_initialized()

        for entry in _HISTORY_CACHE["downloads"]:
            if entry.get("id") == download_id:
                entry["completed_at"] = time.time()
                entry["status"] = "cancelled"
                _persist_history()
                return


def get_download_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent download history."""
    with HISTORY_LOCK:
        _ensure_history_initialized()
        # Return most recent downloads first
        return _HISTORY_CACHE["downloads"][-limit :][::-1]


def get_download_history_json(limit: int = 50) -> str:
    """Get download history as JSON."""
    history = get_download_history(limit)
    return json.dumps({
        "success": True,
        "downloads": history,
        "total_downloaded_bytes": _HISTORY_CACHE.get("total_downloaded_bytes", 0),
    })


def get_download_statistics() -> Dict[str, Any]:
    """Get aggregate download statistics."""
    with HISTORY_LOCK:
        _ensure_history_initialized()

        downloads = _HISTORY_CACHE.get("downloads", [])
        successful = [d for d in downloads if d.get("status") == "success"]
        failed = [d for d in downloads if d.get("status") == "failed"]
        cancelled = [d for d in downloads if d.get("status") == "cancelled"]

        total_size = sum(d.get("bytes_downloaded", 0) for d in successful)
        avg_download_time = 0.0
        if successful:
            times = [d.get("completed_at", 0) - d.get("started_at", 0) for d in successful]
            avg_download_time = sum(times) / len(times) if times else 0

        return {
            "total_downloads": len(downloads),
            "successful_downloads": len(successful),
            "failed_downloads": len(failed),
            "cancelled_downloads": len(cancelled),
            "success_rate": len(successful) / len(downloads) * 100 if downloads else 0,
            "total_bytes_downloaded": total_size,
            "average_download_time_seconds": avg_download_time,
        }


def clear_download_history() -> None:
    """Clear all download history."""
    with HISTORY_LOCK:
        _HISTORY_CACHE["downloads"] = []
        _persist_history()
        logger.log("LuaTools: Download history cleared")
