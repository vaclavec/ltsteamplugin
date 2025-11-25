"""Fix conflict detection system for LuaTools."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from logger import logger
from paths import backend_path
from utils import read_json, write_json

CONFLICT_MATRIX_FILE = "fix_conflicts.json"
CONFLICT_LOCK = threading.Lock()

# In-memory cache
_CONFLICT_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False


def _get_conflict_path() -> str:
    return backend_path(CONFLICT_MATRIX_FILE)


def _ensure_conflicts_initialized() -> None:
    """Initialize conflict matrix file if not exists."""
    global _CONFLICT_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _CONFLICT_CACHE:
        return

    path = _get_conflict_path()
    if os.path.exists(path):
        try:
            _CONFLICT_CACHE = read_json(path)
            _CACHE_INITIALIZED = True
            return
        except Exception as exc:
            logger.warn(f"LuaTools: Failed to load conflict matrix: {exc}")

    # Create default structure
    _CONFLICT_CACHE = {
        "version": 1,
        "created_at": time.time(),
        "game_fixes": {},  # appid: {generic: {}, online: {}, last_applied: time}
        "known_conflicts": [],  # List of known conflict pairs
    }
    _persist_conflicts()
    _CACHE_INITIALIZED = True


def _persist_conflicts() -> None:
    """Write conflict data to disk."""
    try:
        path = _get_conflict_path()
        write_json(path, _CONFLICT_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist conflict matrix: {exc}")


def record_fix_applied(appid: int, fix_type: str, fix_version: str = "", fix_url: str = "") -> None:
    """Record that a fix was applied to a game."""
    with CONFLICT_LOCK:
        _ensure_conflicts_initialized()

        appid_str = str(appid)
        if appid_str not in _CONFLICT_CACHE["game_fixes"]:
            _CONFLICT_CACHE["game_fixes"][appid_str] = {
                "generic": {},
                "online": {},
                "last_applied": 0,
            }

        game_entry = _CONFLICT_CACHE["game_fixes"][appid_str]
        fix_data = {
            "version": fix_version,
            "url": fix_url,
            "applied_at": time.time(),
        }

        if fix_type == "generic":
            game_entry["generic"] = fix_data
        elif fix_type == "online":
            game_entry["online"] = fix_data

        game_entry["last_applied"] = time.time()
        _persist_conflicts()
        logger.log(f"LuaTools: Recorded {fix_type} fix for appid {appid}")


def record_fix_removed(appid: int, fix_type: str) -> None:
    """Record that a fix was removed from a game."""
    with CONFLICT_LOCK:
        _ensure_conflicts_initialized()

        appid_str = str(appid)
        if appid_str in _CONFLICT_CACHE["game_fixes"]:
            game_entry = _CONFLICT_CACHE["game_fixes"][appid_str]
            if fix_type == "generic":
                game_entry["generic"] = {}
            elif fix_type == "online":
                game_entry["online"] = {}
            _persist_conflicts()


def check_for_conflicts(appid: int, proposed_fix_type: str) -> Dict[str, Any]:
    """Check if applying a fix would cause conflicts."""
    with CONFLICT_LOCK:
        _ensure_conflicts_initialized()

        appid_str = str(appid)
        if appid_str not in _CONFLICT_CACHE["game_fixes"]:
            return {
                "appid": appid,
                "has_conflicts": False,
                "conflicts": [],
                "warnings": [],
            }

        game_entry = _CONFLICT_CACHE["game_fixes"][appid_str]
        conflicts = []
        warnings = []

        # Check primary conflicts
        if proposed_fix_type == "online" and game_entry.get("generic"):
            # Applying online fix when generic exists
            conflicts.append({
                "type": "GENERIC_ONLINE_CONFLICT",
                "description": "Generic and Online fixes may conflict. Generic fix will be replaced.",
                "severity": "warning",
                "conflicting_fix": "generic",
            })
            warnings.append("Online fix is recommended for multiplayer. Generic fix will be removed.")

        elif proposed_fix_type == "generic" and game_entry.get("online"):
            # Applying generic fix when online exists
            conflicts.append({
                "type": "ONLINE_GENERIC_CONFLICT",
                "description": "Online and Generic fixes may conflict. Online fix will be replaced.",
                "severity": "warning",
                "conflicting_fix": "online",
            })
            warnings.append("You have an Online fix installed. Applying Generic fix will remove it.")

        # Check for known problematic combinations
        for conflict_pair in _CONFLICT_CACHE.get("known_conflicts", []):
            if (appid in conflict_pair.get("appids", []) and 
                proposed_fix_type in conflict_pair.get("fix_types", [])):
                conflicts.append({
                    "type": conflict_pair.get("type", "KNOWN_CONFLICT"),
                    "description": conflict_pair.get("description", "Known conflict detected"),
                    "severity": conflict_pair.get("severity", "warning"),
                })

        return {
            "appid": appid,
            "has_conflicts": len(conflicts) > 0,
            "conflicts": conflicts,
            "warnings": warnings,
        }


def register_known_conflict(appids: List[int], fix_types: List[str], description: str = "", severity: str = "warning") -> None:
    """Register a known conflict between fixes."""
    with CONFLICT_LOCK:
        _ensure_conflicts_initialized()

        conflict_entry = {
            "appids": appids,
            "fix_types": fix_types,
            "description": description,
            "severity": severity,
            "registered_at": time.time(),
        }

        _CONFLICT_CACHE["known_conflicts"].append(conflict_entry)
        _persist_conflicts()


def get_applied_fixes(appid: int) -> Dict[str, Any]:
    """Get all currently applied fixes for a game."""
    with CONFLICT_LOCK:
        _ensure_conflicts_initialized()

        appid_str = str(appid)
        if appid_str not in _CONFLICT_CACHE["game_fixes"]:
            return {
                "appid": appid,
                "generic": None,
                "online": None,
                "total_fixes": 0,
            }

        game_entry = _CONFLICT_CACHE["game_fixes"][appid_str]
        generic_fix = game_entry.get("generic") if game_entry.get("generic") else None
        online_fix = game_entry.get("online") if game_entry.get("online") else None

        return {
            "appid": appid,
            "generic": generic_fix,
            "online": online_fix,
            "total_fixes": (1 if generic_fix else 0) + (1 if online_fix else 0),
            "last_applied": game_entry.get("last_applied", 0),
        }


def get_conflict_report(appid: int) -> Dict[str, Any]:
    """Get a comprehensive conflict report for a game."""
    applied = get_applied_fixes(appid)
    generic_type = "generic" if applied.get("generic") else None
    online_type = "online" if applied.get("online") else None

    # Determine what the user wants to do and check conflicts
    conflicts_if_add_generic = check_for_conflicts(appid, "generic") if not generic_type else None
    conflicts_if_add_online = check_for_conflicts(appid, "online") if not online_type else None

    return {
        "appid": appid,
        "applied_fixes": applied,
        "potential_conflicts_generic": conflicts_if_add_generic,
        "potential_conflicts_online": conflicts_if_add_online,
        "recommendations": _generate_recommendations(applied),
    }


def _generate_recommendations(applied_fixes: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on applied fixes."""
    recommendations = []

    total = applied_fixes.get("total_fixes", 0)
    if total == 0:
        recommendations.append("No fixes applied. Consider checking if this game needs fixes.")
    elif total == 2:
        recommendations.append("Both generic and online fixes are applied. This is unusual. Consider removing generic fix if online works.")

    generic = applied_fixes.get("generic")
    online = applied_fixes.get("online")

    if generic and not online:
        recommendations.append("Only generic fix applied. For multiplayer games, consider Online fix.")
    elif online and not generic:
        recommendations.append("Online fix applied. Good for multiplayer compatibility.")

    return recommendations


def get_conflict_json(appid: int) -> str:
    """Get conflict report as JSON."""
    report = get_conflict_report(appid)
    return json.dumps({"success": True, "report": report})
