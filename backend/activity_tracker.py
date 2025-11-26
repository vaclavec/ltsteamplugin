"""Real-time activity tracking for live dashboard display."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from logger import logger

# Activity tracking
_ACTIVITY_STATE = {
    "lock": threading.Lock(),
    "current_operations": {},  # op_id: {type, status, progress, started_at}
    "operation_history": [],  # List of completed operations
    "max_history": 100,
}


def start_operation(operation_id: str, op_type: str, description: str = "") -> None:
    """Mark the start of an operation."""
    with _ACTIVITY_STATE["lock"]:
        _ACTIVITY_STATE["current_operations"][operation_id] = {
            "id": operation_id,
            "type": op_type,  # "download", "install", "fix_apply", etc.
            "description": description,
            "status": "starting",
            "progress": 0.0,
            "started_at": time.time(),
            "bytes_total": 0,
            "bytes_current": 0,
            "speed": 0.0,
        }


def update_operation(operation_id: str, status: str = "", progress: float = 0.0, 
                     bytes_total: int = 0, bytes_current: int = 0, speed: float = 0.0) -> None:
    """Update operation progress."""
    with _ACTIVITY_STATE["lock"]:
        if operation_id in _ACTIVITY_STATE["current_operations"]:
            op = _ACTIVITY_STATE["current_operations"][operation_id]
            if status:
                op["status"] = status
            if progress >= 0:
                op["progress"] = min(100.0, progress)
            if bytes_total > 0:
                op["bytes_total"] = bytes_total
            if bytes_current >= 0:
                op["bytes_current"] = bytes_current
            if speed >= 0:
                op["speed"] = speed


def complete_operation(operation_id: str, success: bool = True, error: str = "") -> None:
    """Mark operation as complete."""
    with _ACTIVITY_STATE["lock"]:
        if operation_id in _ACTIVITY_STATE["current_operations"]:
            op = _ACTIVITY_STATE["current_operations"].pop(operation_id)
            op["status"] = "success" if success else "failed"
            op["completed_at"] = time.time()
            if error:
                op["error"] = error
            op["progress"] = 100.0

            _ACTIVITY_STATE["operation_history"].append(op)

            # Trim history
            if len(_ACTIVITY_STATE["operation_history"]) > _ACTIVITY_STATE["max_history"]:
                _ACTIVITY_STATE["operation_history"] = _ACTIVITY_STATE["operation_history"][-_ACTIVITY_STATE["max_history"]:]


def cancel_operation(operation_id: str) -> None:
    """Mark operation as cancelled."""
    with _ACTIVITY_STATE["lock"]:
        if operation_id in _ACTIVITY_STATE["current_operations"]:
            op = _ACTIVITY_STATE["current_operations"].pop(operation_id)
            op["status"] = "cancelled"
            op["completed_at"] = time.time()
            _ACTIVITY_STATE["operation_history"].append(op)


def get_current_operations() -> List[Dict[str, Any]]:
    """Get list of currently active operations."""
    with _ACTIVITY_STATE["lock"]:
        return list(_ACTIVITY_STATE["current_operations"].values())


def get_operation_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get operation history."""
    with _ACTIVITY_STATE["lock"]:
        return _ACTIVITY_STATE["operation_history"][-limit:][::-1]


def get_dashboard_data() -> Dict[str, Any]:
    """Get comprehensive dashboard data for real-time display."""
    with _ACTIVITY_STATE["lock"]:
        current_ops = list(_ACTIVITY_STATE["current_operations"].values())

        # Calculate aggregate statistics
        total_ops = len(current_ops)
        downloading = sum(1 for op in current_ops if op.get("type") == "download")
        installing = sum(1 for op in current_ops if op.get("type") == "install")
        applying_fixes = sum(1 for op in current_ops if op.get("type") == "fix_apply")

        # Calculate total speed (sum of all active downloads)
        total_speed = sum(op.get("speed", 0.0) for op in current_ops if op.get("type") == "download")

        # Calculate total data transferred
        total_bytes = sum(op.get("bytes_current", 0) for op in current_ops)

        # Calculate average progress
        avg_progress = 0.0
        if current_ops:
            avg_progress = sum(op.get("progress", 0.0) for op in current_ops) / len(current_ops)

        return {
            "timestamp": time.time(),
            "current_operations": current_ops,
            "operation_counts": {
                "total": total_ops,
                "downloading": downloading,
                "installing": installing,
                "applying_fixes": applying_fixes,
            },
            "aggregates": {
                "total_speed_bytes_per_sec": total_speed,
                "total_bytes_transferred": total_bytes,
                "average_progress_percent": round(avg_progress, 1),
            },
            "recent_history": _ACTIVITY_STATE["operation_history"][-10:],
        }


def get_dashboard_json() -> str:
    """Get dashboard data as JSON."""
    data = get_dashboard_data()
    return json.dumps({
        "success": True,
        "operations": data.get("current_operations", []),
        "dashboard": data,
    })


def clear_history() -> None:
    """Clear operation history."""
    with _ACTIVITY_STATE["lock"]:
        _ACTIVITY_STATE["operation_history"] = []


def get_operation_statistics() -> Dict[str, Any]:
    """Get statistics from operation history."""
    with _ACTIVITY_STATE["lock"]:
        history = _ACTIVITY_STATE["operation_history"]

        if not history:
            return {
                "total_operations": 0,
                "successful": 0,
                "failed": 0,
                "cancelled": 0,
                "success_rate": 0.0,
                "average_duration_seconds": 0.0,
            }

        successful = sum(1 for op in history if op.get("status") == "success")
        failed = sum(1 for op in history if op.get("status") == "failed")
        cancelled = sum(1 for op in history if op.get("status") == "cancelled")

        durations = [
            op.get("completed_at", op.get("started_at", 0)) - op.get("started_at", 0)
            for op in history
            if op.get("completed_at")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_operations": len(history),
            "successful": successful,
            "failed": failed,
            "cancelled": cancelled,
            "success_rate": (successful / len(history) * 100) if history else 0,
            "average_duration_seconds": round(avg_duration, 2),
        }
