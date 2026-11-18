"""Dhruva triage MCP server (stdio): exposes get_application.
Needs Python 3.10+ and: pip install "mcp>=2"
"""
import logging
import os
import sys
from pathlib import Path

# loader.py reads data/ and decks/ by relative path, and Claude Code starts this
# server from whatever folder the user is in, so anchor everything to this file.
HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

import loader  # noqa: E402
from mcp.server import MCPServer  # noqa: E402

log = logging.getLogger(__name__)  # stderr only: print() would corrupt the stdio channel
mcp = MCPServer("dhruva-triage")


def _err(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


@mcp.tool()
def get_application(app_id: str) -> dict:
    """Fetch one startup application (form fields and deck text) by id, e.g. 'A03'. Read only.

    Failures: NOT_FOUND (do not retry; ask once for a valid id),
    MISSING_FIELD (do not retry; report the field, never guess it),
    DATA_UNAVAILABLE (a data or deck file is missing; report it, do not retry).
    """
    app_id = app_id.strip().upper()
    log.info("get_application %s", app_id)
    try:
        apps = loader.load()
    except KeyError as e:
        return _err("MISSING_FIELD", f"column {e} not found in the CSV")
    except FileNotFoundError as e:
        return _err("DATA_UNAVAILABLE", f"{Path(e.filename).name} not found")
    for a in apps:
        if a["id"] == app_id:
            return {"ok": True, **a}
    return _err("NOT_FOUND", f"no application with id {app_id}")


_OPEN = {}  # app_id -> ticket; lives only as long as this server process


@mcp.tool()
def escalate_to_analyst(app_id: str, reason: str) -> dict:
    """Send an application and a reason to a human analyst. Changes something: it opens a ticket.
    Safe to call twice for the same id: the second call returns the same ticket with already_open true.

    Failures: NOT_FOUND (unknown id, do not retry), INVALID_REASON (empty reason; supply one).
    """
    app_id = app_id.strip().upper()
    log.info("escalate_to_analyst %s", app_id)
    if not reason.strip():
        return _err("INVALID_REASON", "a reason is required")
    if get_application(app_id)["ok"] is False:
        return _err("NOT_FOUND", f"no application with id {app_id}")
    if app_id in _OPEN:
        return {"ok": True, "ticket": _OPEN[app_id], "already_open": True}
    _OPEN[app_id] = f"T-{len(_OPEN) + 1:03d}"
    return {"ok": True, "ticket": _OPEN[app_id], "already_open": False}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)  # goes to stderr
    mcp.run(transport="stdio")
