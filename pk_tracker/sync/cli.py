"""Command line access to sync, independent of the GUI.

    python -m pk_tracker.sync.cli setup     # write the config template
    python -m pk_tracker.sync.cli login     # sign in with Google (opens a browser)
    python -m pk_tracker.sync.cli status    # who am I, when did we last sync
    python -m pk_tracker.sync.cli sync      # merge with the cloud now
    python -m pk_tracker.sync.cli logout

Useful for the first-run setup, for headless machines, and for scripting a
periodic sync without keeping the desktop app open.
"""

from __future__ import annotations

import argparse
import sys

from ..data.db import Database, default_db_path
from .cloudsync import CloudSync, SyncError
from .config import CONFIG_PATH, write_config_template


def _cloud() -> tuple[CloudSync, Database]:
    db = Database(default_db_path())
    return CloudSync(db), db


def cmd_setup(_args) -> int:
    path = write_config_template()
    print(f"Config file: {path}")
    print("Fill in project_id, api_key, oauth_client_id and oauth_client_secret.")
    print("See docs/SYNC.md for where each value comes from.")
    return 0


def cmd_login(_args) -> int:
    cloud, db = _cloud()
    try:
        uid, email = cloud.sign_in()
        print(f"Signed in as {email or uid}")
        return 0
    except SyncError as e:
        print(f"Sign-in failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_logout(_args) -> int:
    cloud, db = _cloud()
    cloud.sign_out()
    db.close()
    print("Signed out on this computer. Your dose log stays on disk.")
    return 0


def cmd_status(_args) -> int:
    cloud, db = _cloud()
    try:
        if not cloud.configured:
            print(f"Sync is not configured. Run 'setup' and edit {CONFIG_PATH}.")
            return 1
        identity = cloud.identity()
        if identity is None:
            print("Configured, but not signed in. Run 'login'.")
            return 1
        uid, email = identity
        print(f"Signed in as {email or '(no email)'}")
        print(f"uid: {uid}")
        print(f"Last sync: {db.get_setting('sync_last_at') or 'never'}")
        return 0
    finally:
        db.close()


def cmd_sync(_args) -> int:
    cloud, db = _cloud()
    try:
        result = cloud.sync_now()
        print(result.summary())
        return 0
    except SyncError as e:
        print(f"Sync failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pk_tracker.sync.cli", description="PK Tracker cloud sync"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, help_text in (
        ("setup", cmd_setup, "write the config template"),
        ("login", cmd_login, "sign in with Google"),
        ("logout", cmd_logout, "forget the signed-in account"),
        ("status", cmd_status, "show sign-in and last sync"),
        ("sync", cmd_sync, "merge with the cloud now"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=fn)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
