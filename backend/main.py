import json
import os
import shutil
import sys
import webbrowser

from typing import Any, List

import Millennium  # type: ignore
import PluginUtils  # type: ignore

from backup_manager import (
    create_backup,
    delete_backup,
    get_backups_list,
    open_backup_location,
    restore_backup,
)
from api_manifest import (
    fetch_free_apis_now as api_fetch_free_apis_now,
    get_init_apis_message as api_get_init_message,
    init_apis as api_init_apis,
    store_last_message,
)
from api_monitor import (
    get_all_api_statuses,
    get_monitor_json,
    is_api_available,
    record_api_request,
)
from activity_tracker import (
    cancel_operation,
    complete_operation,
    get_dashboard_json,
    get_operation_history,
    start_operation,
    update_operation,
)
from auto_update import (
    apply_pending_update_if_any,
    check_for_updates_now as auto_check_for_updates_now,
    restart_steam as auto_restart_steam,
    start_auto_update_background_check,
)
from bandwidth_limiter import (
    disable_throttling,
    enable_throttling,
    get_bandwidth_settings,
    set_bandwidth_limit,
)
from config import WEBKIT_DIR_NAME, WEB_UI_ICON_FILE, WEB_UI_JS_FILE
from download_history import (
    get_download_history_json,
    get_download_statistics,
    record_download_complete,
    record_download_start,
)
from downloads import (
    cancel_add_via_luatools,
    delete_luatools_for_app,
    dismiss_loaded_apps,
    get_add_status,
    get_icon_data_url,
    has_luatools_for_app,
    read_loaded_apps,
    start_add_via_luatools,
)
from fix_conflicts import (
    check_for_conflicts,
    get_conflict_json,
    record_fix_applied,
    record_fix_removed,
)
from fixes import (
    apply_game_fix,
    cancel_apply_fix,
    check_for_fixes,
    get_apply_fix_status,
    get_unfix_status,
    unfix_game,
)
from game_metadata import (
    add_or_update_game,
    get_all_game_metadata,
    get_favorite_games,
    get_game_metadata,
    get_games_by_tag,
    get_metadata_json,
    is_game_favorite,
    search_games,
    set_game_favorite,
    set_game_notes,
    set_game_rating,
    set_game_tags,
)
from script_dependencies import (
    check_for_circular_dependencies,
    check_for_missing_dependencies,
    detect_script_conflicts,
    get_all_dependencies,
    get_dependencies_json,
    register_script,
    resolve_installation_order,
)
from statistics import (
    get_statistics,
    get_statistics_json,
    record_api_fetch,
    record_download,
    record_fix_applied as stats_record_fix_applied,
    record_fix_removed as stats_record_fix_removed,
    record_mod_installed,
    record_mod_removed,
)
from utils import ensure_temp_download_dir
from http_client import close_http_client, ensure_http_client
from logger import logger as shared_logger
from paths import get_plugin_dir, public_path
from settings.manager import (
    apply_settings_changes,
    get_available_locales,
    get_settings_payload,
    get_translation_map,
)
from steam_utils import detect_steam_install_path, get_game_install_path_response, open_game_folder

logger = shared_logger


def GetPluginDir() -> str:  # Legacy API used by the frontend
    return get_plugin_dir()


class Logger:
    @staticmethod
    def log(message: str) -> str:
        shared_logger.log(f"[Frontend] {message}")
        return json.dumps({"success": True})

    @staticmethod
    def warn(message: str) -> str:
        shared_logger.warn(f"[Frontend] {message}")
        return json.dumps({"success": True})

    @staticmethod
    def error(message: str) -> str:
        shared_logger.error(f"[Frontend] {message}")
        return json.dumps({"success": True})


def _steam_ui_path() -> str:
    return os.path.join(Millennium.steam_path(), "steamui", WEBKIT_DIR_NAME)


def _copy_webkit_files() -> None:
    plugin_dir = get_plugin_dir()
    steam_ui_path = _steam_ui_path()
    os.makedirs(steam_ui_path, exist_ok=True)

    js_src = public_path(WEB_UI_JS_FILE)
    js_dst = os.path.join(steam_ui_path, WEB_UI_JS_FILE)
    logger.log(f"Copying LuaTools web UI from {js_src} to {js_dst}")
    try:
        shutil.copy(js_src, js_dst)
    except Exception as exc:
        logger.error(f"Failed to copy LuaTools web UI: {exc}")

    icon_src = public_path(WEB_UI_ICON_FILE)
    icon_dst = os.path.join(steam_ui_path, WEB_UI_ICON_FILE)
    if os.path.exists(icon_src):
        try:
            shutil.copy(icon_src, icon_dst)
            logger.log(f"Copied LuaTools icon to {icon_dst}")
        except Exception as exc:
            logger.error(f"Failed to copy LuaTools icon: {exc}")
    else:
        logger.warn(f"LuaTools icon not found at {icon_src}")


def _inject_webkit_files() -> None:
    js_path = os.path.join(WEBKIT_DIR_NAME, WEB_UI_JS_FILE)
    Millennium.add_browser_js(js_path)
    logger.log(f"LuaTools injected web UI: {js_path}")


def InitApis(contentScriptQuery: str = "") -> str:
    return api_init_apis(contentScriptQuery)


def GetInitApisMessage(contentScriptQuery: str = "") -> str:
    return api_get_init_message(contentScriptQuery)


def FetchFreeApisNow(contentScriptQuery: str = "") -> str:
    return api_fetch_free_apis_now(contentScriptQuery)


def CheckForUpdatesNow(contentScriptQuery: str = "") -> str:
    result = auto_check_for_updates_now()
    return json.dumps(result)


def RestartSteam(contentScriptQuery: str = "") -> str:
    success = auto_restart_steam()
    if success:
        return json.dumps({"success": True})
    return json.dumps({"success": False, "error": "Failed to restart Steam"})


def HasLuaToolsForApp(appid: int, contentScriptQuery: str = "") -> str:
    return has_luatools_for_app(appid)


def StartAddViaLuaTools(appid: int, contentScriptQuery: str = "") -> str:
    return start_add_via_luatools(appid)


def GetAddViaLuaToolsStatus(appid: int, contentScriptQuery: str = "") -> str:
    return get_add_status(appid)


def CancelAddViaLuaTools(appid: int, contentScriptQuery: str = "") -> str:
    return cancel_add_via_luatools(appid)


def GetIconDataUrl(contentScriptQuery: str = "") -> str:
    return get_icon_data_url()


def ReadLoadedApps(contentScriptQuery: str = "") -> str:
    return read_loaded_apps()


def DismissLoadedApps(contentScriptQuery: str = "") -> str:
    return dismiss_loaded_apps()


def DeleteLuaToolsForApp(appid: int, contentScriptQuery: str = "") -> str:
    return delete_luatools_for_app(appid)


def CheckForFixes(appid: int, contentScriptQuery: str = "") -> str:
    return check_for_fixes(appid)


def ApplyGameFix(appid: int, downloadUrl: str, installPath: str, fixType: str = "", gameName: str = "", contentScriptQuery: str = "") -> str:
    return apply_game_fix(appid, downloadUrl, installPath, fixType, gameName)


def GetApplyFixStatus(appid: int, contentScriptQuery: str = "") -> str:
    return get_apply_fix_status(appid)


def CancelApplyFix(appid: int, contentScriptQuery: str = "") -> str:
    return cancel_apply_fix(appid)


def UnFixGame(appid: int, installPath: str = "", contentScriptQuery: str = "") -> str:
    return unfix_game(appid, installPath)


def GetUnfixStatus(appid: int, contentScriptQuery: str = "") -> str:
    return get_unfix_status(appid)


def GetGameInstallPath(appid: int, contentScriptQuery: str = "") -> str:
    result = get_game_install_path_response(appid)
    return json.dumps(result)


def OpenGameFolder(path: str, contentScriptQuery: str = "") -> str:
    success = open_game_folder(path)
    if success:
        return json.dumps({"success": True})
    return json.dumps({"success": False, "error": "Failed to open path"})


def OpenExternalUrl(url: str, contentScriptQuery: str = "") -> str:
    try:
        value = str(url or "").strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            return json.dumps({"success": False, "error": "Invalid URL"})
        if sys.platform.startswith("win"):
            try:
                os.startfile(value)  # type: ignore[attr-defined]
            except Exception:
                webbrowser.open(value)
        else:
            webbrowser.open(value)
        return json.dumps({"success": True})
    except Exception as exc:
        logger.warn(f"LuaTools: OpenExternalUrl failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetSettingsConfig(contentScriptQuery: str = "") -> str:
    try:
        payload = get_settings_payload()
        response = {
            "success": True,
            "schemaVersion": payload.get("version"),
            "schema": payload.get("schema", []),
            "values": payload.get("values", {}),
            "language": payload.get("language"),
            "locales": payload.get("locales", []),
            "translations": payload.get("translations", {}),
        }
        return json.dumps(response)
    except Exception as exc:
        logger.warn(f"LuaTools: GetSettingsConfig failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def ApplySettingsChanges(
    contentScriptQuery: str = "", changes: Any = None, **kwargs: Any
) -> str:  # type: ignore[name-defined]
    try:
        if "changes" in kwargs and changes is None:
            changes = kwargs["changes"]
        if changes is None and isinstance(kwargs, dict):
            changes = kwargs

        try:
            logger.log(
                "LuaTools: ApplySettingsChanges raw argument "
                f"type={type(changes)} value={changes!r}"
            )
            logger.log(f"LuaTools: ApplySettingsChanges kwargs: {kwargs}")
        except Exception:
            pass

        payload: Any = None

        if isinstance(changes, str) and changes:
            try:
                payload = json.loads(changes)
            except Exception:
                logger.warn("LuaTools: Failed to parse changes string payload")
                return json.dumps({"success": False, "error": "Invalid JSON payload"})
            else:
                # When a full payload dict was sent as JSON, unwrap keys we expect.
                if isinstance(payload, dict) and "changes" in payload:
                    kwargs_payload = payload
                    payload = kwargs_payload.get("changes")
                    if "contentScriptQuery" in kwargs_payload and not contentScriptQuery:
                        contentScriptQuery = kwargs_payload.get("contentScriptQuery", "")
                elif isinstance(payload, dict) and "changesJson" in payload and isinstance(payload["changesJson"], str):
                    try:
                        payload = json.loads(payload["changesJson"])
                    except Exception:
                        logger.warn("LuaTools: Failed to parse changesJson string inside payload")
                        return json.dumps({"success": False, "error": "Invalid JSON payload"})
        elif isinstance(changes, dict) and changes:
            # When the bridge passes a dict argument directly.
            if "changesJson" in changes and isinstance(changes["changesJson"], str):
                try:
                    payload = json.loads(changes["changesJson"])
                except Exception:
                    logger.warn("LuaTools: Failed to parse changesJson payload from dict")
                    return json.dumps({"success": False, "error": "Invalid JSON payload"})
            elif "changes" in changes:
                payload = changes.get("changes")
            else:
                payload = changes
        else:
            # Look for JSON payload inside kwargs.
            changes_json = kwargs.get("changesJson")
            if isinstance(changes_json, dict):
                payload = changes_json
            elif isinstance(changes_json, str) and changes_json:
                try:
                    payload = json.loads(changes_json)
                except Exception:
                    logger.warn("LuaTools: Failed to parse changesJson payload")
                    return json.dumps({"success": False, "error": "Invalid JSON payload"})
            elif isinstance(changes_json, dict):
                payload = changes_json
            else:
                payload = changes

        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            logger.warn(f"LuaTools: Parsed payload is not a dict: {payload!r}")
            return json.dumps({"success": False, "error": "Invalid payload format"})

        try:
            logger.log(f"LuaTools: ApplySettingsChanges received payload: {payload}")
        except Exception:
            pass

        result = apply_settings_changes(payload)
        try:
            logger.log(f"LuaTools: ApplySettingsChanges result: {result}")
        except Exception:
            pass
        response = json.dumps(result)
        try:
            logger.log(f"LuaTools: ApplySettingsChanges response json: {response}")
        except Exception:
            pass
        return response
    except Exception as exc:
        logger.warn(f"LuaTools: ApplySettingsChanges failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetAvailableLocales(contentScriptQuery: str = "") -> str:
    try:
        locales = get_available_locales()
        return json.dumps({"success": True, "locales": locales})
    except Exception as exc:
        logger.warn(f"LuaTools: GetAvailableLocales failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetTranslations(contentScriptQuery: str = "", language: str = "", **kwargs: Any) -> str:
    try:
        if not language and "language" in kwargs:
            language = kwargs["language"]
        bundle = get_translation_map(language)
        bundle["success"] = True
        return json.dumps(bundle)
    except Exception as exc:
        logger.warn(f"LuaTools: GetTranslations failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetStatistics(contentScriptQuery: str = "") -> str:
    """Get plugin statistics."""
    try:
        return get_statistics_json()
    except Exception as exc:
        logger.warn(f"LuaTools: GetStatistics failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetDownloadHistory(limit: int = 50, contentScriptQuery: str = "") -> str:
    """Get download history."""
    try:
        return get_download_history_json(limit)
    except Exception as exc:
        logger.warn(f"LuaTools: GetDownloadHistory failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetGameMetadata(appid: int = 0, contentScriptQuery: str = "") -> str:
    """Get game metadata."""
    try:
        if appid > 0:
            return get_metadata_json(appid)
        else:
            return get_metadata_json(None)
    except Exception as exc:
        logger.warn(f"LuaTools: GetGameMetadata failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetGameMetadata(appid: int, app_name: str = "", contentScriptQuery: str = "") -> str:
    """Set or update game metadata."""
    try:
        add_or_update_game(appid, app_name)
        return json.dumps({"success": True, "message": f"Game metadata updated for appid {appid}"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetGameMetadata failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetGameTags(appid: int, tags: List[str] = None, contentScriptQuery: str = "") -> str:
    """Set tags for a game."""
    try:
        if tags is None:
            tags = []
        set_game_tags(appid, tags)
        return json.dumps({"success": True, "message": f"Tags set for appid {appid}"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetGameTags failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetGameNotes(appid: int, notes: str = "", contentScriptQuery: str = "") -> str:
    """Set notes for a game."""
    try:
        set_game_notes(appid, notes)
        return json.dumps({"success": True, "message": f"Notes set for appid {appid}"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetGameNotes failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetGameRating(appid: int, rating: int = 0, contentScriptQuery: str = "") -> str:
    """Set rating for a game (0-5)."""
    try:
        set_game_rating(appid, rating)
        return json.dumps({"success": True, "message": f"Rating set for appid {appid}"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetGameRating failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetGameFavorite(appid: int, is_favorite: bool = False, contentScriptQuery: str = "") -> str:
    """Mark a game as favorite."""
    try:
        set_game_favorite(appid, is_favorite)
        return json.dumps({"success": True, "message": f"Favorite status updated for appid {appid}"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetGameFavorite failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetFavoriteGames(contentScriptQuery: str = "") -> str:
    """Get all favorite games."""
    try:
        favorites = get_favorite_games()
        return json.dumps({"success": True, "games": favorites})
    except Exception as exc:
        logger.warn(f"LuaTools: GetFavoriteGames failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def IsGameFavorite(appid: int, contentScriptQuery: str = "") -> str:
    """Check if a game is marked as favorite."""
    try:
        is_fav = is_game_favorite(appid)
        return json.dumps({"success": True, "isFavorite": is_fav})
    except Exception as exc:
        logger.warn(f"LuaTools: IsGameFavorite failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SearchGames(query: str = "", contentScriptQuery: str = "") -> str:
    """Search games by name, tags, or notes."""
    try:
        results = search_games(query)
        return json.dumps({"success": True, "results": results})
    except Exception as exc:
        logger.warn(f"LuaTools: SearchGames failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetAPIMonitor(contentScriptQuery: str = "") -> str:
    """Get API monitoring statistics."""
    try:
        return get_monitor_json()
    except Exception as exc:
        logger.warn(f"LuaTools: GetAPIMonitor failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def CheckFixConflicts(appid: int, fix_type: str = "generic", contentScriptQuery: str = "") -> str:
    """Check for fix conflicts before applying."""
    try:
        result = check_for_conflicts(appid, fix_type)
        return json.dumps({"success": True, **result})
    except Exception as exc:
        logger.warn(f"LuaTools: CheckFixConflicts failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetScriptDependencies(script_id: str, contentScriptQuery: str = "") -> str:
    """Get script dependency information."""
    try:
        return get_dependencies_json(script_id)
    except Exception as exc:
        logger.warn(f"LuaTools: GetScriptDependencies failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def RegisterScript(script_id: str, name: str = "", version: str = "", dependencies: List[str] = None, contentScriptQuery: str = "") -> str:
    """Register a script with its dependencies."""
    try:
        if dependencies is None:
            dependencies = []
        register_script(script_id, name, version, dependencies)
        return json.dumps({"success": True, "message": f"Script {script_id} registered"})
    except Exception as exc:
        logger.warn(f"LuaTools: RegisterScript failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetActivityDashboard(contentScriptQuery: str = "") -> str:
    """Get real-time activity dashboard data."""
    try:
        return get_dashboard_json()
    except Exception as exc:
        logger.warn(f"LuaTools: GetActivityDashboard failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetBandwidthSettings(contentScriptQuery: str = "") -> str:
    """Get current bandwidth limiting settings."""
    try:
        settings = get_bandwidth_settings()
        return json.dumps({"success": True, "settings": settings})
    except Exception as exc:
        logger.warn(f"LuaTools: GetBandwidthSettings failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def SetBandwidthLimit(max_bytes_per_second: int, contentScriptQuery: str = "") -> str:
    """Set bandwidth limit for downloads."""
    try:
        set_bandwidth_limit(max_bytes_per_second)
        enable_throttling(max_bytes_per_second)
        return json.dumps({"success": True, "message": f"Bandwidth limit set to {max_bytes_per_second} bytes/sec"})
    except Exception as exc:
        logger.warn(f"LuaTools: SetBandwidthLimit failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def DisableBandwidthLimit(contentScriptQuery: str = "") -> str:
    """Disable bandwidth limiting."""
    try:
        disable_throttling()
        return json.dumps({"success": True, "message": "Bandwidth limiting disabled"})
    except Exception as exc:
        logger.warn(f"LuaTools: DisableBandwidthLimit failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def CreateBackup(backup_name: str = "", destination: str = "", contentScriptQuery: str = "") -> str:
    """Create a backup of Steam config folders."""
    try:
        result = create_backup(backup_name, destination)
        return json.dumps(result)
    except Exception as exc:
        logger.warn(f"LuaTools: CreateBackup failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def RestoreBackup(backup_path: str, restore_location: str = "", contentScriptQuery: str = "") -> str:
    """Restore a backup of Steam config folders."""
    try:
        result = restore_backup(backup_path, restore_location)
        return json.dumps(result)
    except Exception as exc:
        logger.warn(f"LuaTools: RestoreBackup failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def GetBackupsList(backup_location: str = "", contentScriptQuery: str = "") -> str:
    """Get list of available backups."""
    try:
        result = get_backups_list(backup_location)
        return json.dumps(result)
    except Exception as exc:
        logger.warn(f"LuaTools: GetBackupsList failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def DeleteBackup(backup_path: str, contentScriptQuery: str = "") -> str:
    """Delete a backup file."""
    try:
        result = delete_backup(backup_path)
        return json.dumps(result)
    except Exception as exc:
        logger.warn(f"LuaTools: DeleteBackup failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


def OpenBackupLocation(backup_path: str, contentScriptQuery: str = "") -> str:
    """Open a backup file location in file manager."""
    try:
        result = open_backup_location(backup_path)
        return json.dumps(result)
    except Exception as exc:
        logger.warn(f"LuaTools: OpenBackupLocation failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})


class Plugin:
    def _front_end_loaded(self):
        _copy_webkit_files()

    def _load(self):
        logger.log(f"bootstrapping LuaTools plugin, millennium {Millennium.version()}")

        try:
            detect_steam_install_path()
        except Exception as exc:
            logger.warn(f"LuaTools: steam path detection failed: {exc}")

        ensure_http_client("InitApis")
        ensure_temp_download_dir()

        try:
            message = apply_pending_update_if_any()
            if message:
                store_last_message(message)
        except Exception as exc:
            logger.warn(f"AutoUpdate: apply pending failed: {exc}")

        _copy_webkit_files()
        _inject_webkit_files()

        try:
            result = InitApis("boot")
            logger.log(f"InitApis (boot) return: {result}")
        except Exception as exc:
            logger.error(f"InitApis (boot) failed: {exc}")

        try:
            start_auto_update_background_check()
        except Exception as exc:
            logger.warn(f"AutoUpdate: start background check failed: {exc}")

        Millennium.ready()

    def _unload(self):
        logger.log("unloading")
        close_http_client("InitApis")


plugin = Plugin()


