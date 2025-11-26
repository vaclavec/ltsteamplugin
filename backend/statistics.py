"""Statistics tracking for LuaTools plugin."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List

from logger import logger
from paths import backend_path
from utils import read_json, write_json

STATS_FILE = "luatools_stats.json"
STATS_LOCK = threading.Lock()

# In-memory cache
_STATS_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False


def _get_stats_path() -> str:
    return backend_path(STATS_FILE)


def _ensure_stats_initialized() -> None:
    """Initialize stats file with default structure if not exists."""
    global _STATS_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _STATS_CACHE:
        return

    path = _get_stats_path()
    if os.path.exists(path):
        _STATS_CACHE = read_json(path)
        _CACHE_INITIALIZED = True
        return

    # Create default stats structure
    _STATS_CACHE = {
        "version": 1,
        "created_at": time.time(),
        "last_updated": time.time(),
        "total_mods_installed": 0,
        "total_games_with_mods": 0,
        "total_fixes_applied": 0,
        "total_games_with_fixes": 0,
        "total_downloads": 0,
        "total_api_fetches": 0,
        "games_with_mods": {},  # appid: {name, date_added, mod_count}
        "games_with_fixes": {},  # appid: {name, date_added, fix_list}
        "daily_stats": {},  # date: {downloads, fixes_applied, mods_added}
    }
    _persist_stats()
    _CACHE_INITIALIZED = True


def _persist_stats() -> None:
    """Write stats to disk."""
    try:
        path = _get_stats_path()
        _STATS_CACHE["last_updated"] = time.time()
        write_json(path, _STATS_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist stats: {exc}")


def record_mod_installed(appid: int, app_name: str = "") -> None:
    """Record that a mod was installed for a game."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        _STATS_CACHE["total_mods_installed"] = _STATS_CACHE.get("total_mods_installed", 0) + 1

        if appid not in _STATS_CACHE["games_with_mods"]:
            _STATS_CACHE["total_games_with_mods"] = _STATS_CACHE.get("total_games_with_mods", 0) + 1
            _STATS_CACHE["games_with_mods"][str(appid)] = {
                "name": app_name,
                "date_added": time.time(),
                "mod_count": 0,
            }

        game_entry = _STATS_CACHE["games_with_mods"].get(str(appid), {})
        game_entry["mod_count"] = game_entry.get("mod_count", 0) + 1
        _STATS_CACHE["games_with_mods"][str(appid)] = game_entry

        _record_daily_stat("mods_added", 1)
        _persist_stats()
        logger.log(f"LuaTools: Recorded mod installation for appid {appid}")


def record_mod_removed(appid: int) -> None:
    """Record that a mod was removed from a game."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        if str(appid) in _STATS_CACHE["games_with_mods"]:
            game_entry = _STATS_CACHE["games_with_mods"][str(appid)]
            mod_count = game_entry.get("mod_count", 1)
            if mod_count > 1:
                game_entry["mod_count"] = mod_count - 1
            else:
                del _STATS_CACHE["games_with_mods"][str(appid)]
                _STATS_CACHE["total_games_with_mods"] = max(0, _STATS_CACHE.get("total_games_with_mods", 1) - 1)
            _persist_stats()


def record_fix_applied(appid: int, app_name: str = "", fix_type: str = "") -> None:
    """Record that a fix was applied to a game."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        _STATS_CACHE["total_fixes_applied"] = _STATS_CACHE.get("total_fixes_applied", 0) + 1

        if appid not in _STATS_CACHE["games_with_fixes"]:
            _STATS_CACHE["total_games_with_fixes"] = _STATS_CACHE.get("total_games_with_fixes", 0) + 1
            _STATS_CACHE["games_with_fixes"][str(appid)] = {
                "name": app_name,
                "date_added": time.time(),
                "fix_list": [],
            }

        game_entry = _STATS_CACHE["games_with_fixes"].get(str(appid), {})
        fix_entry = {
            "type": fix_type,
            "date_applied": time.time(),
        }
        if "fix_list" not in game_entry:
            game_entry["fix_list"] = []
        game_entry["fix_list"].append(fix_entry)
        _STATS_CACHE["games_with_fixes"][str(appid)] = game_entry

        _record_daily_stat("fixes_applied", 1)
        _persist_stats()
        logger.log(f"LuaTools: Recorded fix application for appid {appid}")


def record_fix_removed(appid: int) -> None:
    """Record that a fix was removed from a game."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        if str(appid) in _STATS_CACHE["games_with_fixes"]:
            game_entry = _STATS_CACHE["games_with_fixes"][str(appid)]
            if "fix_list" in game_entry and game_entry["fix_list"]:
                game_entry["fix_list"].pop()
                if not game_entry["fix_list"]:
                    del _STATS_CACHE["games_with_fixes"][str(appid)]
                    _STATS_CACHE["total_games_with_fixes"] = max(0, _STATS_CACHE.get("total_games_with_fixes", 1) - 1)
            _persist_stats()


def record_download(file_size: int = 0, success: bool = True) -> None:
    """Record a download event."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        _STATS_CACHE["total_downloads"] = _STATS_CACHE.get("total_downloads", 0) + 1
        _record_daily_stat("downloads", 1)
        if file_size > 0:
            _STATS_CACHE["total_bytes_downloaded"] = _STATS_CACHE.get("total_bytes_downloaded", 0) + file_size
        _persist_stats()


def record_api_fetch(success: bool = True) -> None:
    """Record an API fetch event."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        _STATS_CACHE["total_api_fetches"] = _STATS_CACHE.get("total_api_fetches", 0) + 1
        _persist_stats()


def _record_daily_stat(stat_name: str, value: int) -> None:
    """Record a daily statistic."""
    today = time.strftime("%Y-%m-%d", time.localtime())
    if today not in _STATS_CACHE["daily_stats"]:
        _STATS_CACHE["daily_stats"][today] = {}
    daily = _STATS_CACHE["daily_stats"][today]
    daily[stat_name] = daily.get(stat_name, 0) + value


def get_statistics() -> Dict[str, Any]:
    """Return current statistics."""
    with STATS_LOCK:
        _ensure_stats_initialized()
        
        # Calculate last 7 days downloads
        today = time.time()
        seven_days_ago = today - (7 * 24 * 3600)
        last_7_days_downloads = 0
        for date_str, daily_stat in _STATS_CACHE.get("daily_stats", {}).items():
            try:
                date_time = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
                if date_time >= seven_days_ago:
                    last_7_days_downloads += daily_stat.get("downloads", 0)
            except Exception:
                pass
        
        return {
            "total_mods_installed": _STATS_CACHE.get("total_mods_installed", 0),
            "total_games_with_mods": _STATS_CACHE.get("total_games_with_mods", 0),
            "total_fixes_applied": _STATS_CACHE.get("total_fixes_applied", 0),
            "total_games_with_fixes": _STATS_CACHE.get("total_games_with_fixes", 0),
            "total_downloads": _STATS_CACHE.get("total_downloads", 0),
            "total_api_fetches": _STATS_CACHE.get("total_api_fetches", 0),
            "total_bytes_downloaded": _STATS_CACHE.get("total_bytes_downloaded", 0),
            "games_with_mods": list(_STATS_CACHE.get("games_with_mods", {}).values()),
            "games_with_fixes": list(_STATS_CACHE.get("games_with_fixes", {}).values()),
            "last_7_days_downloads": last_7_days_downloads,
        }


def get_statistics_json() -> str:
    """Return statistics as JSON string."""
    import json
    stats = get_statistics()
    stats["success"] = True
    return json.dumps(stats)
