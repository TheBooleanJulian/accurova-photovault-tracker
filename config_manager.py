"""
config_manager.py
Handles loading/saving persistent app settings so the user doesn't have to
re-enter folders, sheet ID, credentials path etc. every time.

Config is stored at: ~/.photovault_tracker/config.json

OAuth client credentials are read from the environment first (GOOGLE_OAUTH_CLIENT_ID /
GOOGLE_OAUTH_CLIENT_SECRET, optionally loaded from a .env file next to this script).
The client-secret JSON path in config is only a fallback.
"""

import json
import os

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".photovault_tracker")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "root_folders": [],
    "sheet_id": "",
    "oauth_client_secret_path": "",
    "oauth_token_path": os.path.join(CONFIG_DIR, "authorized_user.json"),
    "scan_cache_path": os.path.join(CONFIG_DIR, "last_scan_cache.json"),
    "raw_extensions": ["nef", "cr2", "cr3", "arw", "dng", "raf", "orf", "rw2"],
    "processed_extensions": ["jpg", "jpeg", "png", "tif", "tiff", "heic"],
    "fully_processed_threshold": 90,
}


def load_config() -> dict:
    """Load config from disk, falling back to defaults for any missing keys."""
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config: dict) -> None:
    """Persist config to disk, creating the directory if needed."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_env(path: str = ENV_PATH) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (existing env vars win)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_credentials_available() -> bool:
    return bool(os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"))


load_env()
