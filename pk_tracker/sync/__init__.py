"""Cross-device sync of the dose log.

The desktop app talks to the same Firebase project as the Android app, over
plain HTTPS REST (no SDK, no extra dependencies): sign in with Google, exchange
the Google identity for a Firebase one, then read and write
``users/{uid}/doses/{doseUid}`` in Firestore. Because both apps authenticate as
the same Google account they land on the same ``uid``, so the two logs converge.
"""

from .config import SyncConfig, load_config
from .cloudsync import CloudSync, SyncResult

__all__ = ["SyncConfig", "load_config", "CloudSync", "SyncResult"]
