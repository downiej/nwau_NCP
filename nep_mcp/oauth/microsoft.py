"""Microsoft Entra ID v2.0 helpers.

Two responsibilities:
    1. Build the /authorize URL we redirect the user to.
    2. Exchange the auth code (returned by Microsoft to our callback) for an
       ID token, and pull out the user's email + display name.

We don't validate Microsoft's ID token signature here because the auth code
arrives over a back-channel HTTPS POST that we initiate — possession of the
code over that channel is the assertion. The ID token's claims (email, name)
are used only for embedding identity into our own JWTs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import urllib.parse

import httpx


log = logging.getLogger(__name__)

GRAPH_SCOPES = "openid profile email offline_access"


def authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


def authorize_url(
    tenant_id: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    base = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": GRAPH_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # Force re-consent for the very first sign-in of each user so they
        # see exactly what we're asking for. After that Entra remembers.
        "prompt": "select_account",
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def make_pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def exchange_code(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> dict:
    """Swap an auth code for tokens at Microsoft's /token endpoint.

    Returns the parsed JSON token response (id_token, access_token, etc.).
    Raises httpx.HTTPStatusError on non-2xx.
    """
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope": GRAPH_SCOPES,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, data=data)
        if r.status_code >= 400:
            log.warning("Microsoft /token rejected: %s %s", r.status_code, r.text[:300])
            r.raise_for_status()
        return r.json()


def claims_from_id_token(id_token: str) -> dict:
    """Decode the ID token's payload without signature check.

    Safe here because the token came directly from Microsoft over HTTPS in
    response to our authenticated /token POST — no untrusted middleman.
    """
    parts = id_token.split(".")
    if len(parts) != 3:
        return {}
    pad = "=" * (-len(parts[1]) % 4)
    payload = base64.urlsafe_b64decode(parts[1] + pad)
    return json.loads(payload)
