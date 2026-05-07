"""Azure Functions entry point — wraps the FastMCP ASGI app.

Uses ``AsgiFunctionApp`` (azure-functions >= 1.18) instead of the older
``AsgiMiddleware``. ``AsgiFunctionApp`` runs the ASGI lifespan protocol,
which is required because MCP's streamable-http session manager starts
its task group inside its lifespan handler — without that, every request
500s with "Task group is not initialized."

App settings expected in Azure (or local.settings.json for `func start`):
    NEP_API_KEY   - required in production; protects every request
    NEP_PRICE     - optional override (defaults to 7258)
    NEP_XLSX_PATH - optional; defaults to bundled price_weights/*.xlsx
    NEP_YEAR      - optional label, e.g. "2025-26"
"""

from __future__ import annotations

import logging

import azure.functions as func

from nep_mcp.auth import install as install_auth
from nep_mcp.config import load_settings
from nep_mcp.server import build_app


log = logging.getLogger(__name__)


# Build once per worker — the xlsx parse happens at cold start and stays
# resident for every subsequent invocation on this instance.
_settings = load_settings()
_asgi_app = build_app()
install_auth(_asgi_app, _settings.api_key)


app = func.AsgiFunctionApp(app=_asgi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
