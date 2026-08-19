"""Filesystem layout and installation discovery.

Extracted verbatim from server.py. Everything that answers "where does this
live" belongs here: the payload root, the runtime state directory under
%LOCALAPPDATA%, the database and config paths, and the resolution of the FIFA
installation itself.

Importing this module creates the runtime data and log directories, which is
the same side effect the block had inside server.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


APP_NAME = "FIFA15 Local FUT"
VERSION = "0.2.43-current-season-reset-fix"
ROOT = Path(__file__).resolve().parent
# Keep runtime state outside the FIFA installation directory. FIFA is commonly
# installed under Program Files, where a normal user cannot create SQLite/log
# files. Configuration remains beside server.py, while mutable state goes to
# %%LOCALAPPDATA%%\FIFA15LocalFUT.
_local_app_data = os.environ.get("LOCALAPPDATA")
if _local_app_data:
    RUNTIME_ROOT = Path(_local_app_data) / "FIFA15LocalFUT"
else:
    RUNTIME_ROOT = Path.home() / "AppData" / "Local" / "FIFA15LocalFUT"
DATA = RUNTIME_ROOT / "data"
LOGS = RUNTIME_ROOT / "logs"
# v0.2.29 promotes the SQLite save to the LocalAppData profile root so every
# future build shares one obvious, version-independent club database.  Older
# builds stored the same database one level deeper under data\.
LEGACY_DB_PATH = DATA / "localfut15.sqlite3"
DB_PATH = RUNTIME_ROOT / "fut15-local.sqlite3"
CONFIG_PATH = ROOT / "config.json"
# A second copy of the port map lives in a machine-wide folder. PLAY_LOCAL_FUT15
# always runs elevated, so when UAC elevates into a different administrator
# account the launcher no longer shares LOCALAPPDATA with this process and would
# never find the per-profile copy.
_program_data = os.environ.get("ProgramData")
if _program_data:
    SHARED_PORTS_PATH = Path(_program_data) / "FIFA15LocalFUT" / "runtime_ports.json"
else:
    SHARED_PORTS_PATH = None


def _resolve_game_root() -> tuple[Path, str]:
    """Locate the FIFA 15 installation.

    The Local FUT payload no longer has to be copied inside the FIFA folder, so
    the game directory is resolved explicitly instead of being inferred from
    where this file happens to sit.  Order:

      1. LOCALFUT_GAME_DIR environment variable (per-run override).
      2. game_dir in install.json, in the FIFA15LocalFUT folder under
         %LOCALAPPDATA%, as written by DEPLOY_TO_GAME.cmd.
      3. ROOT.parent - the historical layout, where the whole payload was copied
         into the game folder.  Keeping this last means an old-style install
         still works untouched.

    A candidate is only accepted if fifa15.exe is actually in it, so a stale
    install.json cannot silently divert cl.ini/EA-MITM.ini to a dead path.
    """
    candidates: list[tuple[Path, str]] = []

    env_dir = os.environ.get("LOCALFUT_GAME_DIR")
    if env_dir:
        candidates.append((Path(env_dir), "LOCALFUT_GAME_DIR"))

    install_path = RUNTIME_ROOT / "install.json"
    try:
        # utf-8-sig: DEPLOY_TO_GAME.cmd writes this through PowerShell,
        # whose Set-Content -Encoding utf8 emits a BOM that plain utf-8
        # decoding leaves in front of the "{" and json.loads rejects.
        raw = json.loads(install_path.read_text(encoding="utf-8-sig"))
        configured = str(raw.get("game_dir", "") or "").strip()
        if configured:
            candidates.append((Path(configured), str(install_path)))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    for candidate, source in candidates:
        try:
            if (candidate / "fifa15.exe").is_file():
                return candidate.resolve(), source
        except OSError:
            continue

    return ROOT.parent, "payload location (legacy layout)"


GAME_ROOT, GAME_ROOT_SOURCE = _resolve_game_root()

DATA.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
