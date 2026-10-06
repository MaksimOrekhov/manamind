"""Live Power.log bridge: tail, reduce, gate, sanitize and emit decision snapshots.

V1 stops at a trusted, settled, sanitized state plus server-validated legal actions.
There is no recommendation, search, network or overlay code here.
"""

SNAPSHOT_SCHEMA = "manamind.live.snapshot/1"
STATUS_SCHEMA = "manamind.live.status/1"
