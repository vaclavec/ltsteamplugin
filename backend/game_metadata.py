"""Game metadata storage for enhanced game information."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from logger import logger
from paths import backend_path
from utils import read_json, write_json

GAME_METADATA_FILE = "game_metadata.json"
METADATA_LOCK = threading.Lock()

# In-memory cache
_METADATA_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False


def _get_metadata_path() -> str:
    return backend_path(GAME_METADATA_FILE)


def _ensure_metadata_initialized() -> None:
    """Initialize metadata file if not exists."""
    global _METADATA_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _METADATA_CACHE:
        return

    path = _get_metadata_path()
    if os.path.exists(path):
        try:
            _METADATA_CACHE = read_json(path)
            _CACHE_INITIALIZED = True
            return
        except Exception as exc:
            logger.warn(f"LuaTools: Failed to load game metadata: {exc}")

    # Create default metadata structure
    _METADATA_CACHE = {
        "version": 1,
        "created_at": time.time(),
        "games": {},  # appid: {name, tags, notes, rating, favorite, custom_data}
    }
    _persist_metadata()
    _CACHE_INITIALIZED = True


def _persist_metadata() -> None:
    """Write metadata to disk."""
    try:
        path = _get_metadata_path()
        write_json(path, _METADATA_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist game metadata: {exc}")


def add_or_update_game(appid: int, app_name: str) -> None:
    """Add or update a game in metadata."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {
                "name": app_name,
                "tags": [],
                "notes": "",
                "rating": 0,
                "favorite": False,
                "added_at": time.time(),
                "last_modified": time.time(),
            }
        else:
            _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()

        _persist_metadata()


def set_game_tags(appid: int, tags: List[str]) -> None:
    """Set tags for a game."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {"tags": []}

        _METADATA_CACHE["games"][appid_str]["tags"] = list(set(tags))  # Remove duplicates
        _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
        _persist_metadata()


def add_game_tag(appid: int, tag: str) -> None:
    """Add a tag to a game."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {"tags": []}

        tags = _METADATA_CACHE["games"][appid_str].get("tags", [])
        if tag not in tags:
            tags.append(tag)
            _METADATA_CACHE["games"][appid_str]["tags"] = tags
            _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
            _persist_metadata()


def remove_game_tag(appid: int, tag: str) -> None:
    """Remove a tag from a game."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str in _METADATA_CACHE["games"]:
            tags = _METADATA_CACHE["games"][appid_str].get("tags", [])
            if tag in tags:
                tags.remove(tag)
                _METADATA_CACHE["games"][appid_str]["tags"] = tags
                _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
                _persist_metadata()


def set_game_notes(appid: int, notes: str) -> None:
    """Set notes for a game."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {}

        _METADATA_CACHE["games"][appid_str]["notes"] = str(notes)[:1000]  # Max 1000 chars
        _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
        _persist_metadata()


def set_game_rating(appid: int, rating: int) -> None:
    """Set personal rating for a game (0-5)."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {}

        # Clamp rating to 0-5
        clamped_rating = max(0, min(5, int(rating)))
        _METADATA_CACHE["games"][appid_str]["rating"] = clamped_rating
        _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
        _persist_metadata()


def set_game_favorite(appid: int, is_favorite: bool) -> None:
    """Mark a game as favorite or not."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str not in _METADATA_CACHE["games"]:
            _METADATA_CACHE["games"][appid_str] = {}

        _METADATA_CACHE["games"][appid_str]["favorite"] = bool(is_favorite)
        _METADATA_CACHE["games"][appid_str]["last_modified"] = time.time()
        _persist_metadata()


def get_game_metadata(appid: int) -> Dict[str, Any]:
    """Get metadata for a specific game."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        appid_str = str(appid)
        if appid_str in _METADATA_CACHE["games"]:
            return _METADATA_CACHE["games"][appid_str].copy()

        return {
            "name": "",
            "tags": [],
            "notes": "",
            "rating": 0,
            "favorite": False,
        }


def get_all_game_metadata() -> Dict[str, Dict[str, Any]]:
    """Get metadata for all games."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()
        return {k: v.copy() for k, v in _METADATA_CACHE["games"].items()}


def get_favorite_games() -> List[Dict[str, Any]]:
    """Get all favorite games."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        favorites = []
        for appid_str, metadata in _METADATA_CACHE["games"].items():
            if metadata.get("favorite", False):
                favorites.append({
                    "appid": int(appid_str),
                    "name": metadata.get("name", ""),
                    **metadata,
                })
        return sorted(favorites, key=lambda x: x.get("last_modified", 0), reverse=True)


def is_game_favorite(appid: int) -> bool:
    """Check if a specific game is marked as favorite."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()
        appid_str = str(appid)
        game = _METADATA_CACHE["games"].get(appid_str, {})
        return game.get("favorite", False)


def get_games_by_tag(tag: str) -> List[Dict[str, Any]]:
    """Get all games with a specific tag."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        games = []
        for appid_str, metadata in _METADATA_CACHE["games"].items():
            if tag in metadata.get("tags", []):
                games.append({
                    "appid": int(appid_str),
                    **metadata,
                })
        return games


def search_games(query: str) -> List[Dict[str, Any]]:
    """Search games by name, tags, or notes."""
    with METADATA_LOCK:
        _ensure_metadata_initialized()

        query_lower = query.lower()
        results = []

        for appid_str, metadata in _METADATA_CACHE["games"].items():
            name = metadata.get("name", "").lower()
            notes = metadata.get("notes", "").lower()
            tags = [tag.lower() for tag in metadata.get("tags", [])]

            if (query_lower in name or 
                query_lower in notes or 
                any(query_lower in tag for tag in tags)):
                results.append({
                    "appid": int(appid_str),
                    **metadata,
                })

        return results


def get_metadata_json(appid: Optional[int] = None) -> str:
    """Get metadata as JSON."""
    if appid is not None:
        metadata = get_game_metadata(appid)
        return json.dumps({"success": True, "metadata": metadata})
    else:
        all_metadata = get_all_game_metadata()
        return json.dumps({"success": True, "metadata": all_metadata})
