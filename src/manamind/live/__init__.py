"""Live Power.log bridge: tail, reduce, gate, sanitize and emit decision snapshots.

The bridge owns trusted, settled, sanitized state and server-validated legal actions.
The separate policy adapter ranks current actions read-only; there is no search or overlay.
"""

SNAPSHOT_SCHEMA = "manamind.live.snapshot/1"
STATUS_SCHEMA = "manamind.live.status/1"
