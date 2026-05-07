"""Azure Functions entry point — wraps the FastMCP ASGI app.

Uses ``AsgiFunctionApp`` (azure-functions >= 1.18) which handles the ASGI
lifespan protocol — required because MCP's streamable-http session manager
starts its task group inside its lifespan handler.

Authentication is handled by FastMCP itself when OAuth env vars are set:
``server.build_app()`` wires a Microsoft Entra ID OAuth broker that requires
a bearer token on every MCP request.

App settings expected in Azure (or local.settings.json for `func start`):
    NEP_PRICE                  - optional override (defaults to 7258)
    NEP_XLSX_PATH              - optional; defaults to bundled price_weights/*.xlsx
    NEP_YEAR                   - optional label, e.g. "2025-26"
    NEP_PUBLIC_URL             - https://<host>/  (required for OAuth metadata)
    NEP_ALLOWED_HOSTS          - csv of host headers MCP transport should accept
    NEP_OAUTH_TENANT_ID        - Entra tenant id
    NEP_OAUTH_CLIENT_ID        - Entra app reg client id
    NEP_OAUTH_CLIENT_SECRET    - Entra app reg client secret
    NEP_OAUTH_JWT_SECRET       - HS256 key we sign our own access tokens with
"""

from __future__ import annotations

import logging

import azure.functions as func

from nep_mcp.server import build_app


log = logging.getLogger(__name__)


# Build once per worker — xlsx parse + OAuth provider construction happen at
# cold start and stay resident for every subsequent invocation on this worker.
_asgi_app = build_app()


app = func.AsgiFunctionApp(app=_asgi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
