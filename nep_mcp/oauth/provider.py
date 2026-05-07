"""MCP-spec OAuthAuthorizationServerProvider that brokers to Microsoft Entra ID.

Flow per request:

  Claude Desktop                MCP server (this)              Microsoft Entra ID
  -----------------             --------------------           -------------------
   POST /register      ---->   register_client()
                              <----  client_id, client_secret
   GET /authorize      ---->   authorize() -- builds Microsoft URL
                              <----  302 to Microsoft
                                                                 user signs in
                                                       <----  302 back to /oauth/microsoft_callback
                              microsoft_callback() -- exchanges code, mints OUR auth code
                              <----  302 to Claude's redirect_uri with our code
   POST /token         ---->   exchange_authorization_code()
                              <----  our access JWT (signed by us, contains user email)
   POST /mcp/...       ---->   bearer middleware verifies our JWT
                              <----  tool result

Tokens we issue are HS256-signed JWTs containing: sub (user email), name,
client_id, scopes, exp. The bearer middleware is set up by FastMCP via the
`token_verifier` we expose.
"""

from __future__ import annotations

import logging
import secrets
import time

import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthToken,
    RefreshToken,
    TokenVerifier,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from ..config import OAuthConfig
from . import microsoft
from .state import PendingAuthorization, store


log = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 60 * 60          # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
AUTH_CODE_TTL_SECONDS = 60                  # 1 minute (Claude redeems immediately)


class MicrosoftBrokerProvider(OAuthAuthorizationServerProvider):
    """Implements the MCP OAuth provider Protocol with Microsoft as upstream IdP."""

    def __init__(self, oauth_cfg: OAuthConfig):
        if not oauth_cfg.is_configured():
            raise RuntimeError(
                "OAuth is enabled but tenant_id/client_id/client_secret/jwt_secret "
                "are not all set. Check NEP_OAUTH_* environment variables."
            )
        self.cfg = oauth_cfg

    # ------------------------------------------------------------------ DCR
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return store.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # FastMCP fills in client_id/secret if absent; we just persist.
        if not client_info.client_id:
            client_info.client_id = secrets.token_urlsafe(24)
        if not client_info.client_secret:
            client_info.client_secret = secrets.token_urlsafe(32)
        client_info.client_id_issued_at = int(time.time())
        client_info.client_secret_expires_at = 0  # never
        store.clients[client_info.client_id] = client_info
        log.info("Registered MCP client %s (%s)", client_info.client_id,
                 client_info.client_name or "unnamed")

    # ------------------------------------------------------------ /authorize
    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        verifier, challenge = microsoft.make_pkce_pair()
        state_id = secrets.token_urlsafe(32)

        store.pending[state_id] = PendingAuthorization(
            state_id=state_id,
            client_id=client.client_id,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            requested_scopes=params.scopes or [],
            client_state=params.state,
            resource=params.resource,
            pkce_verifier_for_microsoft=verifier,
        )
        store.cleanup()

        return microsoft.authorize_url(
            tenant_id=self.cfg.tenant_id,
            client_id=self.cfg.client_id,
            redirect_uri=self.cfg.microsoft_redirect_uri,
            state=state_id,
            code_challenge=challenge,
        )

    # --------- Called by routes.py after Microsoft sends the user back to us
    async def complete_microsoft_callback(self, ms_code: str, state_id: str) -> str:
        """Returns a 302-target URL to send the Claude client onward to."""
        pending = store.pending.pop(state_id, None)
        if pending is None:
            raise ValueError("Unknown or expired authorization state")

        token_resp = await microsoft.exchange_code(
            tenant_id=self.cfg.tenant_id,
            client_id=self.cfg.client_id,
            client_secret=self.cfg.client_secret,
            redirect_uri=self.cfg.microsoft_redirect_uri,
            code=ms_code,
            code_verifier=pending.pkce_verifier_for_microsoft,
        )

        claims = microsoft.claims_from_id_token(token_resp.get("id_token", ""))
        user_email = (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("upn")
            or claims.get("oid", "unknown")
        )
        user_name = claims.get("name") or user_email

        # Mint our own authorization code and remember the user we authenticated.
        our_code = secrets.token_urlsafe(32)
        client = store.clients.get(pending.client_id)
        if client is None:
            raise ValueError(f"Client {pending.client_id} no longer registered")

        store.codes[our_code] = AuthorizationCode(
            code=our_code,
            scopes=pending.requested_scopes or ["mcp.access"],
            expires_at=time.time() + AUTH_CODE_TTL_SECONDS,
            client_id=pending.client_id,
            code_challenge=pending.code_challenge,
            redirect_uri=AnyUrl(pending.redirect_uri),
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            resource=pending.resource,
        )
        # Stash user identity keyed by code so token exchange can embed it.
        store.codes[our_code]._user_email = user_email   # type: ignore[attr-defined]
        store.codes[our_code]._user_name = user_name     # type: ignore[attr-defined]

        return construct_redirect_uri(
            pending.redirect_uri,
            code=our_code,
            state=pending.client_state,
        )

    # ------------------------------------------------------------- /token
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = store.codes.get(authorization_code)
        if code is None:
            return None
        if code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            store.codes.pop(authorization_code, None)
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        code_obj = store.codes.pop(authorization_code.code, None)
        if code_obj is None:
            raise ValueError("Authorization code already redeemed")

        user_email = getattr(code_obj, "_user_email", "unknown")
        user_name = getattr(code_obj, "_user_name", user_email)

        access = self._mint_access_token(
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            user_email=user_email,
            user_name=user_name,
        )
        refresh = self._mint_refresh_token(
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            user_email=user_email,
            user_name=user_name,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        try:
            claims = jwt.decode(
                refresh_token,
                self.cfg.jwt_secret,
                algorithms=[JWT_ALGORITHM],
                audience="nep-mcp-refresh",
            )
        except jwt.PyJWTError:
            return None
        if claims.get("client_id") != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=claims.get("scopes", []),
            expires_at=int(claims.get("exp", 0)),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Decode the refresh token to recover user identity for the new access token.
        claims = jwt.decode(
            refresh_token.token,
            self.cfg.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            audience="nep-mcp-refresh",
        )
        access = self._mint_access_token(
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes,
            user_email=claims.get("sub", "unknown"),
            user_name=claims.get("name", "unknown"),
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes or refresh_token.scopes),
            refresh_token=refresh_token.token,
        )

    async def revoke_token(self, token) -> None:  # noqa: ARG002
        # In-memory state has no per-token store to delete from (stateless JWTs);
        # short TTL + refresh-token rotation is the revocation strategy.
        return None

    # ----------------------------------------------------- Token verification
    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self.cfg.jwt_secret,
                algorithms=[JWT_ALGORITHM],
                audience="nep-mcp-access",
            )
        except jwt.PyJWTError as exc:
            log.debug("Bearer token rejected: %s", exc)
            return None
        return AccessToken(
            token=token,
            client_id=claims.get("client_id", ""),
            scopes=claims.get("scopes", []),
            expires_at=int(claims.get("exp", 0)),
            resource=None,
        )

    # ---------------------------------------------------------------- helpers
    def _mint_access_token(
        self, *, client_id: str, scopes: list[str], user_email: str, user_name: str
    ) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": str(self.cfg.issuer_url),
                "sub": user_email,
                "name": user_name,
                "aud": "nep-mcp-access",
                "client_id": client_id,
                "scopes": scopes,
                "iat": now,
                "exp": now + ACCESS_TOKEN_TTL_SECONDS,
            },
            self.cfg.jwt_secret,
            algorithm=JWT_ALGORITHM,
        )

    def _mint_refresh_token(
        self, *, client_id: str, scopes: list[str], user_email: str, user_name: str
    ) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": str(self.cfg.issuer_url),
                "sub": user_email,
                "name": user_name,
                "aud": "nep-mcp-refresh",
                "client_id": client_id,
                "scopes": scopes,
                "iat": now,
                "exp": now + REFRESH_TOKEN_TTL_SECONDS,
            },
            self.cfg.jwt_secret,
            algorithm=JWT_ALGORITHM,
        )


class BrokerTokenVerifier(TokenVerifier):
    """Adapter so FastMCP's bearer middleware can verify our self-issued JWTs."""

    def __init__(self, provider: MicrosoftBrokerProvider):
        self._provider = provider

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self._provider.load_access_token(token)
