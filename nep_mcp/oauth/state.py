"""In-memory stores for OAuth broker state.

Each Flex Consumption worker holds its own copy. That is acceptable for
single-instance / low-volume use because:
- Authorization codes live <60 s and are redeemed immediately by the same
  Claude client that requested them — short enough that a worker recycle
  during the window is rare and recoverable (the user just retries).
- Registered clients are persisted per-worker; if a client lands on a fresh
  worker after registration it will re-register transparently (DCR is cheap).
- Access tokens are self-contained JWTs validated by signature, not looked
  up here, so they survive worker churn fine.

If we ever scale beyond one instance, these dicts move to Redis or Cosmos.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingAuthorization:
    """Tracks an in-flight /authorize call until Microsoft callback returns.

    state_id is the value we pass to Microsoft as the OAuth `state` param;
    when Microsoft redirects back to /oauth/microsoft_callback we use it to
    re-hydrate the original Claude client's request and emit our own auth code.
    """

    state_id: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    requested_scopes: list[str]
    client_state: str | None
    resource: str | None
    pkce_verifier_for_microsoft: str
    created_at: float = field(default_factory=time.time)


class _Store:
    """Thread-safe lazy-cleanup store for the three OAuth state collections."""

    def __init__(self):
        self._lock = threading.Lock()
        self.clients: dict[str, Any] = {}              # client_id -> OAuthClientInformationFull
        self.pending: dict[str, PendingAuthorization] = {}
        self.codes: dict[str, Any] = {}                # code -> AuthorizationCode (MCP)
        self.refresh: dict[str, Any] = {}              # token -> RefreshToken (MCP)

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            for sid, p in list(self.pending.items()):
                if now - p.created_at > 600:           # 10 min cap on auth flow
                    self.pending.pop(sid, None)
            for code, c in list(self.codes.items()):
                exp = getattr(c, "expires_at", 0)
                if exp and exp < now:
                    self.codes.pop(code, None)


store = _Store()
