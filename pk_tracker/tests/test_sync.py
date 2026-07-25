"""Sync tests: wire encoding, and the last-write-wins merge.

The network is faked -- a dict-backed stand-in for the Firestore collection --
so the merge semantics can be pinned down exactly. What is verified here is the
contract shared with the Android app: field names, epoch-millisecond timestamps,
tombstones that stay deleted, and convergence when both sides have changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pk_tracker.data.db import Database
from pk_tracker.sync.cloudsync import CloudSync, SyncError, _from_epoch_ms, _to_epoch_ms
from pk_tracker.sync.config import SyncConfig
from pk_tracker.sync.firestore import decode_fields, encode_fields

NOW = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
CONFIG = SyncConfig(project_id="p", api_key="k", oauth_client_id="c")


class FakeFirestore:
    """Stands in for FirestoreClient, keeping documents in memory."""

    def __init__(self, documents: dict | None = None):
        self.documents = documents or {}
        self.writes: list[str] = []

    def list_documents(self, _collection):
        return dict(self.documents)

    def put_document(self, _collection, doc_id, data):
        self.documents[doc_id] = data
        self.writes.append(doc_id)


@pytest.fixture
def db():
    d = Database(None)          # in-memory, seeded with the builtin substances
    yield d
    d.close()


def _sync(db, remote=None):
    """A CloudSync wired to a fake collection, bypassing auth/network."""
    cloud = CloudSync(db, config=CONFIG)
    fake = FakeFirestore(remote)
    return cloud, fake


def _remote_dose(substance="caffeine", amount=90.0, taken=NOW, updated=NOW, deleted=False):
    return {
        "substanceId": substance,
        "amount": amount,
        "unit": "mg",
        "takenAtEpochMs": _to_epoch_ms(taken.isoformat()),
        "note": "",
        "deleted": deleted,
        "updatedAt": _to_epoch_ms(updated.isoformat()),
    }


# ----- encoding --------------------------------------------------------------
def test_firestore_round_trip_preserves_types():
    data = {"s": "x", "i": 1753430400000, "f": 90.5, "b": True}
    decoded = decode_fields(encode_fields(data))
    assert decoded == data
    assert isinstance(decoded["i"], int)
    assert isinstance(decoded["b"], bool)


def test_integers_are_encoded_as_strings_like_firestore_expects():
    encoded = encode_fields({"updatedAt": 1753430400000})
    assert encoded["fields"]["updatedAt"] == {"integerValue": "1753430400000"}


def test_bool_is_not_encoded_as_an_integer():
    # bool subclasses int in Python; the encoder must check bool first.
    assert encode_fields({"deleted": False})["fields"]["deleted"] == {"booleanValue": False}


def test_epoch_ms_round_trip():
    assert _from_epoch_ms(_to_epoch_ms(NOW.isoformat())) == NOW


# ----- pulling ---------------------------------------------------------------
def test_pull_inserts_remote_dose(db):
    cloud, fake = _sync(db, {"uid-1": _remote_dose()})
    result = cloud._merge_remote(fake.documents)
    assert result.inserted == 1
    doses = db.list_doses("caffeine")
    assert len(doses) == 1
    assert doses[0].amount == 90.0
    assert doses[0].taken_at == NOW


def test_pull_is_idempotent(db):
    cloud, fake = _sync(db, {"uid-1": _remote_dose()})
    cloud._merge_remote(fake.documents)
    second = cloud._merge_remote(fake.documents)
    assert (second.inserted, second.updated) == (0, 0)
    assert len(db.list_doses("caffeine")) == 1


def test_newer_remote_wins(db):
    cloud, fake = _sync(db, {"uid-1": _remote_dose(amount=90.0)})
    cloud._merge_remote(fake.documents)
    fake.documents["uid-1"] = _remote_dose(amount=120.0, updated=NOW + timedelta(hours=1))
    result = cloud._merge_remote(fake.documents)
    assert result.updated == 1
    assert db.list_doses("caffeine")[0].amount == 120.0


def test_older_remote_is_ignored(db):
    cloud, fake = _sync(db, {"uid-1": _remote_dose(amount=90.0)})
    cloud._merge_remote(fake.documents)
    fake.documents["uid-1"] = _remote_dose(amount=10.0, updated=NOW - timedelta(hours=1))
    result = cloud._merge_remote(fake.documents)
    assert result.updated == 0
    assert db.list_doses("caffeine")[0].amount == 90.0


def test_remote_tombstone_removes_the_dose(db):
    cloud, fake = _sync(db, {"uid-1": _remote_dose()})
    cloud._merge_remote(fake.documents)
    assert len(db.list_doses("caffeine")) == 1

    fake.documents["uid-1"] = _remote_dose(deleted=True, updated=NOW + timedelta(minutes=5))
    cloud._merge_remote(fake.documents)
    assert db.list_doses("caffeine") == []
    # the tombstone is kept so the deletion can propagate onward
    assert db.dose_row_by_uid("uid-1")["deleted"] == 1


def test_unknown_substance_is_skipped_not_fatal(db):
    cloud, fake = _sync(db, {
        "uid-1": _remote_dose(substance="nootropic-x"),
        "uid-2": _remote_dose(),
    })
    result = cloud._merge_remote(fake.documents)
    assert result.skipped_unknown_substance == 1
    assert result.inserted == 1        # the known one still made it in


def test_malformed_document_is_ignored(db):
    cloud, fake = _sync(db, {"uid-1": {"substanceId": "caffeine"}})   # no updatedAt
    result = cloud._merge_remote(fake.documents)
    assert (result.inserted, result.updated) == (0, 0)


# ----- pushing ---------------------------------------------------------------
def test_push_uploads_local_doses(db):
    db.add_dose("caffeine", 80, "mg", NOW)
    cloud, fake = _sync(db)
    pushed = cloud._push_local(fake, "c", {})
    assert pushed == 1
    doc = next(iter(fake.documents.values()))
    assert doc["substanceId"] == "caffeine"
    assert doc["amount"] == 80.0
    assert isinstance(doc["takenAtEpochMs"], int)
    assert doc["deleted"] is False


def test_push_skips_rows_the_cloud_already_has(db):
    db.add_dose("caffeine", 80, "mg", NOW)
    cloud, fake = _sync(db)
    cloud._push_local(fake, "c", {})
    again = cloud._push_local(fake, "c", dict(fake.documents))
    assert again == 0


def test_local_deletion_is_pushed_as_a_tombstone(db):
    dose = db.add_dose("caffeine", 80, "mg", NOW)
    cloud, fake = _sync(db)
    cloud._push_local(fake, "c", {})
    db.delete_dose(dose.id)
    cloud._push_local(fake, "c", dict(fake.documents))
    assert next(iter(fake.documents.values()))["deleted"] is True


def test_round_trip_between_two_devices_converges(db):
    """A dose logged here, pulled by a peer, edited there, comes back edited."""
    db.add_dose("caffeine", 80, "mg", NOW)
    cloud, fake = _sync(db)
    cloud._push_local(fake, "c", {})

    doc_id = next(iter(fake.documents))
    peer_edit = dict(fake.documents[doc_id])
    peer_edit["amount"] = 150.0
    peer_edit["updatedAt"] = peer_edit["updatedAt"] + 60_000
    fake.documents[doc_id] = peer_edit

    cloud._merge_remote(fake.documents)
    assert db.list_doses("caffeine")[0].amount == 150.0
    # and the settled state does not bounce back on the next push
    assert cloud._push_local(fake, "c", dict(fake.documents)) == 0


# ----- guard rails -----------------------------------------------------------
def test_sync_without_config_raises():
    d = Database(None)
    try:
        with pytest.raises(SyncError):
            CloudSync(d, config=None).sync_now()
    finally:
        d.close()
