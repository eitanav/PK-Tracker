"""A very small Firestore REST client.

Only what the dose log needs: list a collection and write a document. Firestore's
REST encoding wraps every field in a type tag (and, awkwardly, sends 64-bit ints
as JSON *strings*), so the encode/decode helpers here are the bulk of the work.

The document shape matches the Android app exactly -- see ``CloudSync.toMap`` in
``android/.../sync/CloudSync.kt``. Keep the two in step or the apps will read
each other's rows as empty.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://firestore.googleapis.com/v1"
_PAGE_SIZE = 300


class FirestoreError(RuntimeError):
    """A Firestore request failed."""


def _encode_value(value) -> dict:
    # bool first: in Python bool is a subclass of int.
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if value is None:
        return {"nullValue": None}
    return {"stringValue": str(value)}


def _decode_value(value: dict):
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "nullValue" in value:
        return None
    return value.get("stringValue", "")


def encode_fields(data: dict) -> dict:
    return {"fields": {k: _encode_value(v) for k, v in data.items()}}


def decode_fields(document: dict) -> dict:
    return {k: _decode_value(v) for k, v in (document.get("fields") or {}).items()}


class FirestoreClient:
    """Reads and writes one user's documents, authenticated as that user."""

    def __init__(self, project_id: str, id_token: str):
        self.project_id = project_id
        self.id_token = id_token

    def _url(self, path: str) -> str:
        return f"{_BASE}/projects/{self.project_id}/databases/(default)/documents/{path}"

    def _request(self, url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {self.id_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            if e.code in (401, 403):
                raise FirestoreError(
                    f"Firestore rejected the request ({e.code}). Check that you are "
                    f"signed in and that the security rules allow this user: {detail}"
                ) from e
            raise FirestoreError(f"Firestore request failed ({e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise FirestoreError(f"network error contacting Firestore: {e.reason}") from e

    def list_documents(self, collection: str) -> dict[str, dict]:
        """Every document in ``collection``, keyed by document id."""
        out: dict[str, dict] = {}
        page_token = ""
        while True:
            query = {"pageSize": _PAGE_SIZE}
            if page_token:
                query["pageToken"] = page_token
            url = f"{self._url(collection)}?{urllib.parse.urlencode(query)}"
            data = self._request(url)
            for doc in data.get("documents", []):
                doc_id = doc.get("name", "").rsplit("/", 1)[-1]
                if doc_id:
                    out[doc_id] = decode_fields(doc)
            page_token = data.get("nextPageToken", "")
            if not page_token:
                return out

    def put_document(self, collection: str, doc_id: str, data: dict) -> None:
        """Create or overwrite a document (equivalent to the Android SDK's ``set``)."""
        # PATCH with no updateMask replaces the document wholesale.
        self._request(
            self._url(f"{collection}/{doc_id}"),
            method="PATCH",
            payload=encode_fields(data),
        )
