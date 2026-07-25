"""Merge the local dose log with the cloud copy.

Mirrors the Android app's ``CloudSync`` exactly: the collection is
``users/{uid}/doses/{doseUid}``, the merge is last-write-wins on ``updatedAt``,
and soft-deleted rows travel as tombstones so a deletion on one device does not
come back to life from another.

One representation difference is bridged here: the desktop stores timestamps as
ISO 8601 strings, while the wire format (set by the Android app) uses epoch
milliseconds. All conversion happens in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..data.db import Database
from . import auth
from .config import SyncConfig, load_config
from .firestore import FirestoreClient, FirestoreError

COLLECTION = "users/{uid}/doses"


class SyncError(RuntimeError):
    """Sync could not complete."""


@dataclass
class SyncResult:
    """What one sync run actually did, for reporting in the UI."""

    inserted: int = 0
    updated: int = 0
    pushed: int = 0
    skipped_unknown_substance: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.pushed)

    def summary(self) -> str:
        if self.skipped_unknown_substance:
            extra = f", {self.skipped_unknown_substance} skipped (unknown substance)"
        else:
            extra = ""
        if not self.changed:
            return "Already up to date" + extra
        return (
            f"{self.inserted} new, {self.updated} updated, "
            f"{self.pushed} uploaded" + extra
        )


def _to_epoch_ms(iso: str) -> int:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _from_epoch_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class CloudSync:
    """Sync orchestration. Construct with the app's ``Database``."""

    def __init__(self, db: Database, config: SyncConfig | None = None):
        self.db = db
        self.config = config if config is not None else load_config()

    # ----- state -------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return self.config is not None and self.config.complete

    def identity(self) -> tuple[str, str] | None:
        """``(uid, email)`` when signed in, else ``None``."""
        if not self.configured:
            return None
        creds = auth.valid_credentials(self.config)
        return (creds.uid, creds.email) if creds else None

    # ----- auth --------------------------------------------------------------
    def sign_in(self) -> tuple[str, str]:
        if not self.configured:
            raise SyncError(
                "Sync is not configured yet. See docs/SYNC.md for the one-time setup."
            )
        creds = auth.sign_in(self.config)
        return creds.uid, creds.email

    def sign_out(self) -> None:
        auth.sign_out()

    # ----- the merge ---------------------------------------------------------
    def sync_now(self) -> SyncResult:
        """Pull the cloud in, then push anything local it is missing."""
        if not self.configured:
            raise SyncError(
                "Sync is not configured yet. See docs/SYNC.md for the one-time setup."
            )
        creds = auth.valid_credentials(self.config)
        if creds is None:
            raise SyncError("Not signed in. Sign in with Google to sync.")

        client = FirestoreClient(self.config.project_id, creds.id_token)
        collection = COLLECTION.format(uid=creds.uid)
        try:
            remote = client.list_documents(collection)
            result = self._merge_remote(remote)
            result.pushed = self._push_local(client, collection, remote)
        except FirestoreError as e:
            raise SyncError(str(e)) from e

        self.db.set_setting("sync_last_at", datetime.now(timezone.utc).isoformat())
        return result

    def _merge_remote(self, remote: dict[str, dict]) -> SyncResult:
        result = SyncResult()
        known = self.db.known_substance_ids()
        for doc_id, fields in remote.items():
            substance_id = fields.get("substanceId") or ""
            updated_at = fields.get("updatedAt")
            if not substance_id or updated_at is None:
                continue                      # not a dose document we understand
            if substance_id not in known:
                # doses.substance_id is a foreign key; inserting would fail. Count
                # it so the UI can say what was left behind rather than lying.
                result.skipped_unknown_substance += 1
                continue
            outcome = self.db.upsert_synced_dose(
                uid=doc_id,
                substance_id=substance_id,
                amount=float(fields.get("amount") or 0.0),
                unit=str(fields.get("unit") or "mg"),
                taken_at=_from_epoch_ms(int(fields.get("takenAtEpochMs") or 0)),
                note=str(fields.get("note") or ""),
                deleted=bool(fields.get("deleted")),
                updated_at=_from_epoch_ms(int(updated_at)),
            )
            if outcome == "inserted":
                result.inserted += 1
            elif outcome == "updated":
                result.updated += 1
        return result

    def _push_local(
        self, client: FirestoreClient, collection: str, remote: dict[str, dict]
    ) -> int:
        pushed = 0
        for row in self.db.all_for_sync():
            uid = row.get("uid")
            if not uid or not row.get("updated_at"):
                continue
            local_ms = _to_epoch_ms(row["updated_at"])
            remote_doc = remote.get(uid)
            if remote_doc is not None:
                remote_ms = int(remote_doc.get("updatedAt") or 0)
                if local_ms <= remote_ms:
                    continue
            client.put_document(collection, uid, self._to_wire(row, local_ms))
            pushed += 1
        return pushed

    @staticmethod
    def _to_wire(row: dict, updated_ms: int) -> dict:
        """Field names and types must match the Android app's document shape."""
        return {
            "substanceId": row["substance_id"],
            "amount": float(row["amount"]),
            "unit": row["unit"],
            "takenAtEpochMs": _to_epoch_ms(row["taken_at"]),
            "note": row["note"] or "",
            "deleted": bool(row["deleted"]),
            "updatedAt": updated_ms,
        }
