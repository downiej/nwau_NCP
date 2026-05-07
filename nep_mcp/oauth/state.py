"""OAuth state — Azure Table Storage backed (with in-memory fallback for local dev).

Three logical stores live in a single table per kind:
    oauthClients  - rowkey=client_id, value=OAuthClientInformationFull JSON
    oauthPending  - rowkey=state_id,  value=PendingAuthorization JSON
    oauthCodes    - rowkey=code,      value=AuthorizationCode JSON + user identity

We persist because Azure Functions Flex Consumption can route consecutive
requests in the same OAuth flow to different workers / processes:

    POST /register      -> worker A   (registers client_id X)
    GET  /authorize     -> worker B   (looks up X -> not found, error)

Table Storage is shared, so any worker can resolve any client/code.

If NEP_OAUTH_STATE_CONN is unset we fall back to a process-local dict — that
keeps the unit tests, CI, and `python -m nep_mcp` dev mode working without
needing a storage account.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from mcp.server.auth.provider import AuthorizationCode
from mcp.shared.auth import OAuthClientInformationFull


log = logging.getLogger(__name__)

TABLE_CLIENTS = "oauthClients"
TABLE_PENDING = "oauthPending"
TABLE_CODES = "oauthCodes"
PARTITION = "default"


@dataclass
class PendingAuthorization:
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


# ----------------------------------------------------------- Backend selection
def _connection_string() -> str | None:
    return (
        os.environ.get("NEP_OAUTH_STATE_CONN")
        or os.environ.get("AzureWebJobsStorage")
        or None
    )


class _MemoryBackend:
    """Process-local fallback used when no storage connection is configured."""

    def __init__(self):
        self._lock = threading.Lock()
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.pending: dict[str, PendingAuthorization] = {}
        self.codes: dict[str, dict[str, Any]] = {}

    def put_client(self, c: OAuthClientInformationFull) -> None:
        with self._lock:
            self.clients[c.client_id] = c

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    def put_pending(self, p: PendingAuthorization) -> None:
        with self._lock:
            self.pending[p.state_id] = p

    def pop_pending(self, state_id: str) -> PendingAuthorization | None:
        with self._lock:
            return self.pending.pop(state_id, None)

    def put_code(self, code: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self.codes[code] = payload

    def get_code(self, code: str) -> dict[str, Any] | None:
        return self.codes.get(code)

    def pop_code(self, code: str) -> dict[str, Any] | None:
        with self._lock:
            return self.codes.pop(code, None)


class _TableBackend:
    """Persists OAuth state to Azure Table Storage so it survives worker churn."""

    def __init__(self, conn: str):
        from azure.data.tables import TableServiceClient
        self._svc = TableServiceClient.from_connection_string(conn)
        self._tables: dict[str, Any] = {}
        for name in (TABLE_CLIENTS, TABLE_PENDING, TABLE_CODES):
            self._svc.create_table_if_not_exists(name)
            self._tables[name] = self._svc.get_table_client(name)
        log.info("OAuth state backend: Azure Table Storage")

    def _put(self, table: str, row_key: str, payload: dict[str, Any]) -> None:
        entity = {"PartitionKey": PARTITION, "RowKey": row_key, "data": json.dumps(payload)}
        self._tables[table].upsert_entity(entity)

    def _get(self, table: str, row_key: str) -> dict[str, Any] | None:
        try:
            entity = self._tables[table].get_entity(PARTITION, row_key)
        except Exception:
            return None
        return json.loads(entity["data"])

    def _delete(self, table: str, row_key: str) -> dict[str, Any] | None:
        existing = self._get(table, row_key)
        if existing is not None:
            try:
                self._tables[table].delete_entity(PARTITION, row_key)
            except Exception:
                pass
        return existing

    # ---- clients
    def put_client(self, c: OAuthClientInformationFull) -> None:
        self._put(TABLE_CLIENTS, c.client_id, c.model_dump(mode="json"))

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self._get(TABLE_CLIENTS, client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    # ---- pending
    def put_pending(self, p: PendingAuthorization) -> None:
        self._put(TABLE_PENDING, p.state_id, asdict(p))

    def pop_pending(self, state_id: str) -> PendingAuthorization | None:
        data = self._delete(TABLE_PENDING, state_id)
        return PendingAuthorization(**data) if data else None

    # ---- codes
    def put_code(self, code: str, payload: dict[str, Any]) -> None:
        self._put(TABLE_CODES, code, payload)

    def get_code(self, code: str) -> dict[str, Any] | None:
        return self._get(TABLE_CODES, code)

    def pop_code(self, code: str) -> dict[str, Any] | None:
        return self._delete(TABLE_CODES, code)


def _select_backend():
    conn = _connection_string()
    if not conn:
        log.warning("OAuth state backend: in-memory (single-process only)")
        return _MemoryBackend()
    try:
        return _TableBackend(conn)
    except Exception:
        log.exception("Falling back to in-memory state — Table Storage init failed")
        return _MemoryBackend()


_backend = _select_backend()


# -------------------------------------------------- Public store-style facade
class _Store:
    """Public interface used by provider.py — same shape as before but durable."""

    def __init__(self, backend):
        self._b = backend

    # clients
    @property
    def clients(self):
        # provider.py uses dict-like access; build a tiny shim
        return _ClientFacade(self._b)

    # pending
    @property
    def pending(self):
        return _PendingFacade(self._b)

    # codes
    @property
    def codes(self):
        return _CodeFacade(self._b)

    def cleanup(self) -> None:
        # Pending and codes have natural expiry baked in — Table Storage doesn't
        # auto-prune, but the caller checks expires_at before honouring them, so
        # stale rows are functionally inert. A daily timer trigger could sweep.
        pass


class _ClientFacade:
    def __init__(self, backend):
        self._b = backend

    def __setitem__(self, client_id: str, client: OAuthClientInformationFull) -> None:
        self._b.put_client(client)

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._b.get_client(client_id)


class _PendingFacade:
    def __init__(self, backend):
        self._b = backend

    def __setitem__(self, state_id: str, pending: PendingAuthorization) -> None:
        self._b.put_pending(pending)

    def pop(self, state_id: str, default=None):
        result = self._b.pop_pending(state_id)
        return result if result is not None else default


class _CodeFacade:
    """Stores a dict-shaped payload per code. provider.py reads/writes it
    via item access, so we shim get/setitem/pop here.
    """

    def __init__(self, backend):
        self._b = backend

    def __setitem__(self, code: str, value: dict | AuthorizationCode) -> None:
        if isinstance(value, AuthorizationCode):
            payload = value.model_dump(mode="json")
        else:
            payload = dict(value)
        self._b.put_code(code, payload)

    def __getitem__(self, code: str):
        data = self._b.get_code(code)
        if data is None:
            raise KeyError(code)
        return _CodeRow(self._b, code, data)

    def get(self, code: str):
        data = self._b.get_code(code)
        return _CodeRow(self._b, code, data) if data is not None else None

    def pop(self, code: str, default=None):
        data = self._b.pop_code(code)
        return _CodeRow(self._b, code, data) if data is not None else default


class _CodeRow:
    """Reconstitutes an AuthorizationCode from its stored JSON, with the
    out-of-band user identity stored alongside (provider.py reads them via
    `getattr(code, '_user_email', ...)`).
    """

    def __init__(self, backend, code_str: str, data: dict[str, Any]):
        self._b = backend
        self._code_str = code_str
        self._auth_code = AuthorizationCode.model_validate(
            {k: v for k, v in data.items() if not k.startswith("_user_")}
        )
        # Re-attach the side-channel identity attrs
        self._user_email = data.get("_user_email", "unknown")
        self._user_name = data.get("_user_name", self._user_email)

    # Pass-through to AuthorizationCode for everything pricing code reads
    def __getattr__(self, name: str):
        if name in ("_user_email", "_user_name"):
            raise AttributeError(name)
        return getattr(self._auth_code, name)


# What provider.py imports
store = _Store(_backend)
