"""Script dependency resolver for Lua script management."""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Set

from logger import logger
from paths import backend_path
from utils import read_json, write_json

DEPENDENCIES_FILE = "script_dependencies.json"
DEPS_LOCK = threading.Lock()

# In-memory cache
_DEPS_CACHE: Dict[str, Any] = {}
_CACHE_INITIALIZED = False


def _get_deps_path() -> str:
    return backend_path(DEPENDENCIES_FILE)


def _ensure_deps_initialized() -> None:
    """Initialize dependencies file if not exists."""
    global _DEPS_CACHE, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and _DEPS_CACHE:
        return

    path = _get_deps_path()
    if os.path.exists(path):
        try:
            _DEPS_CACHE = read_json(path)
            _CACHE_INITIALIZED = True
            return
        except Exception as exc:
            logger.warn(f"LuaTools: Failed to load script dependencies: {exc}")

    # Create default structure
    _DEPS_CACHE = {
        "version": 1,
        "scripts": {},  # script_id: {name, version, dependencies: [], required_by: []}
    }
    _persist_deps()
    _CACHE_INITIALIZED = True


def _persist_deps() -> None:
    """Write dependencies to disk."""
    try:
        path = _get_deps_path()
        write_json(path, _DEPS_CACHE)
    except Exception as exc:
        logger.warn(f"LuaTools: Failed to persist script dependencies: {exc}")


def register_script(script_id: str, name: str = "", version: str = "", dependencies: Optional[List[str]] = None) -> None:
    """Register a script and its dependencies."""
    with DEPS_LOCK:
        _ensure_deps_initialized()

        dependencies = dependencies or []
        _DEPS_CACHE["scripts"][script_id] = {
            "name": name,
            "version": version,
            "dependencies": list(set(dependencies)),  # Remove duplicates
            "required_by": [],
        }

        # Update reverse dependencies
        for dep_id in dependencies:
            if dep_id not in _DEPS_CACHE["scripts"]:
                _DEPS_CACHE["scripts"][dep_id] = {
                    "name": "",
                    "version": "",
                    "dependencies": [],
                    "required_by": [],
                }
            if script_id not in _DEPS_CACHE["scripts"][dep_id]["required_by"]:
                _DEPS_CACHE["scripts"][dep_id]["required_by"].append(script_id)

        _persist_deps()
        logger.log(f"LuaTools: Registered script {script_id} with {len(dependencies)} dependencies")


def get_script_dependencies(script_id: str) -> List[str]:
    """Get direct dependencies of a script."""
    with DEPS_LOCK:
        _ensure_deps_initialized()

        if script_id in _DEPS_CACHE["scripts"]:
            return _DEPS_CACHE["scripts"][script_id].get("dependencies", [])
        return []


def get_all_dependencies(script_id: str) -> Set[str]:
    """Get all transitive dependencies of a script (recursive)."""
    visited: Set[str] = set()

    def _traverse(script: str) -> None:
        if script in visited:
            return
        visited.add(script)

        with DEPS_LOCK:
            _ensure_deps_initialized()
            if script in _DEPS_CACHE["scripts"]:
                for dep in _DEPS_CACHE["scripts"][script].get("dependencies", []):
                    _traverse(dep)

    _traverse(script_id)
    visited.discard(script_id)  # Don't include the script itself
    return visited


def check_for_missing_dependencies(script_id: str, installed_scripts: List[str]) -> Dict[str, Any]:
    """Check if a script has missing dependencies."""
    all_deps = get_all_dependencies(script_id)
    installed_set = set(installed_scripts)
    missing = all_deps - installed_set

    return {
        "script_id": script_id,
        "all_dependencies": list(all_deps),
        "installed_dependencies": list(all_deps & installed_set),
        "missing_dependencies": list(missing),
        "has_missing": len(missing) > 0,
    }


def get_dependent_scripts(script_id: str) -> List[str]:
    """Get all scripts that depend on this script."""
    with DEPS_LOCK:
        _ensure_deps_initialized()

        if script_id in _DEPS_CACHE["scripts"]:
            return _DEPS_CACHE["scripts"][script_id].get("required_by", [])
        return []


def check_for_circular_dependencies(script_id: str) -> Dict[str, Any]:
    """Check if a script has circular dependencies."""
    visited: Set[str] = set()
    path: List[str] = []

    def _detect_cycle(script: str) -> Optional[List[str]]:
        if script in visited:
            if script in path:
                # Found cycle
                cycle_start = path.index(script)
                return path[cycle_start:] + [script]
            return None

        visited.add(script)
        path.append(script)

        with DEPS_LOCK:
            _ensure_deps_initialized()
            if script in _DEPS_CACHE["scripts"]:
                for dep in _DEPS_CACHE["scripts"][script].get("dependencies", []):
                    cycle = _detect_cycle(dep)
                    if cycle:
                        return cycle

        path.pop()
        return None

    cycle = _detect_cycle(script_id)

    return {
        "script_id": script_id,
        "has_circular_dependency": cycle is not None,
        "cycle": cycle,
    }


def resolve_installation_order(script_ids: List[str]) -> Dict[str, Any]:
    """Resolve the correct installation order for a group of scripts."""
    all_scripts = set(script_ids)

    # Add all transitive dependencies
    all_needed: Set[str] = set()
    for script in script_ids:
        all_needed.add(script)
        all_needed.update(get_all_dependencies(script))

    # Topological sort
    ordered: List[str] = []
    visited: Set[str] = set()

    def _visit(script: str) -> bool:
        if script in visited:
            return True

        # Check for circular dependency
        if not _check_circular(script, script, set()):
            return False

        visited.add(script)

        # Visit dependencies first
        with DEPS_LOCK:
            _ensure_deps_initialized()
            if script in _DEPS_CACHE["scripts"]:
                for dep in _DEPS_CACHE["scripts"][script].get("dependencies", []):
                    if dep in all_needed:
                        if not _visit(dep):
                            return False

        ordered.append(script)
        return True

    def _check_circular(current: str, target: str, path: Set[str]) -> bool:
        """Check if there's a path from current to target (cycle detection)."""
        with DEPS_LOCK:
            _ensure_deps_initialized()
            if current in path:
                return False
            path.add(current)

            if current in _DEPS_CACHE["scripts"]:
                for dep in _DEPS_CACHE["scripts"][current].get("dependencies", []):
                    if dep == target:
                        return True
                    if _check_circular(dep, target, path.copy()):
                        return True
        return False

    # Attempt to visit all scripts
    for script in all_needed:
        if not _visit(script):
            return {
                "success": False,
                "error": f"Circular dependency detected involving {script}",
                "installation_order": [],
                "new_dependencies": [],
            }

    new_dependencies = list(all_needed - set(script_ids))

    return {
        "success": True,
        "installation_order": ordered,
        "new_dependencies": new_dependencies,
        "total_scripts": len(ordered),
        "message": f"Install in this order: {' → '.join(ordered)}",
    }


def detect_script_conflicts(script_ids: List[str]) -> List[Dict[str, Any]]:
    """Detect known conflicts between scripts."""
    # This would be populated with community-reported conflicts
    # For now, return empty list
    conflicts = []

    # Future: Load from conflicts database
    # For now, just check for obvious issues
    if len(script_ids) > 10:
        conflicts.append({
            "severity": "warning",
            "message": "Installing many scripts can impact performance",
            "scripts": script_ids,
        })

    return conflicts


def get_dependencies_json(script_id: str) -> str:
    """Get dependency information as JSON."""
    missing_check = check_for_missing_dependencies(script_id, [])
    circular_check = check_for_circular_dependencies(script_id)
    dependents = get_dependent_scripts(script_id)

    return json.dumps({
        "success": True,
        "script_id": script_id,
        "dependencies": missing_check,
        "circular": circular_check,
        "dependents": dependents,
    })
