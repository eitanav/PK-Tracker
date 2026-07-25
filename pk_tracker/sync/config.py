"""Firebase/Google credentials for sync.

These identify the Firebase project and the OAuth client, and are deliberately
kept **out of the repository** (it is public). They live in
``~/.pk_tracker/firebase.json`` or in environment variables, so a fresh clone
never carries someone else's project.

Note that none of these are passwords: the Firebase Web API key and an installed
app's OAuth client id/secret are all client-side identifiers that ship inside
every distributed binary. What actually protects the data is the Firestore
security rules (a signed-in user may only touch ``users/{their own uid}``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".pk_tracker" / "firebase.json"

_FIELDS = ("project_id", "api_key", "oauth_client_id", "oauth_client_secret")


@dataclass
class SyncConfig:
    """Everything needed to authenticate and reach Firestore."""

    project_id: str
    api_key: str
    oauth_client_id: str
    oauth_client_secret: str = ""     # installed-app clients: not confidential

    @property
    def complete(self) -> bool:
        return bool(self.project_id and self.api_key and self.oauth_client_id)


def load_config(path: str | Path | None = None) -> SyncConfig | None:
    """Load sync config from the environment, else from ``firebase.json``.

    Returns ``None`` when sync has not been configured, so callers can offer to
    set it up instead of crashing.
    """
    env = {f: os.environ.get(f"PK_TRACKER_{f.upper()}", "") for f in _FIELDS}
    if env["project_id"] and env["api_key"] and env["oauth_client_id"]:
        return SyncConfig(**env)

    p = Path(path) if path is not None else CONFIG_PATH
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    cfg = SyncConfig(**{f: str(raw.get(f, "")) for f in _FIELDS})
    return cfg if cfg.complete else None


def write_config_template(path: str | Path | None = None) -> Path:
    """Write a blank ``firebase.json`` for the user to fill in. Never overwrites."""
    p = Path(path) if path is not None else CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(
            json.dumps({f: "" for f in _FIELDS}, indent=2) + "\n", encoding="utf-8"
        )
    return p
