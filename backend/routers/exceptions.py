"""
exceptions.py — Read-only API view of the agent whitelist rules.
Returns the static whitelist data from agent/exceptions.py so the dashboard
can display which paths, extensions, and processes are currently suppressed.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/exceptions", tags=["exceptions"])


@router.get("")
async def list_exceptions():
    from agent.exceptions import (
        WHITELISTED_PROCESSES,
        WHITELISTED_PATH_PREFIXES,
        WHITELISTED_EXTENSIONS,
        TEMP_DIR_PREFIXES,
        SUSPICIOUS_EXTENSIONS_IN_TEMP,
    )
    return {
        "processes": sorted(WHITELISTED_PROCESSES),
        "path_prefixes": sorted(WHITELISTED_PATH_PREFIXES),
        "extensions": sorted(WHITELISTED_EXTENSIONS),
        "temp_dir_prefixes": list(TEMP_DIR_PREFIXES),
        "suspicious_extensions_in_temp": sorted(SUSPICIOUS_EXTENSIONS_IN_TEMP),
    }
