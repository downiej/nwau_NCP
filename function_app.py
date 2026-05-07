"""Azure Functions entry point — wraps the FastMCP ASGI app.

The MCP streamable-http transport is a Starlette app; Azure Functions for
Python (v2 model) supports ASGI directly via AsgiMiddleware. We attach the
API-key middleware in front, then forward every request under /mcp/* to the
ASGI app.

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


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.function_name(name="mcp_endpoint")
@app.route(
    route="{*path}",
    methods=[func.HttpMethod.GET, func.HttpMethod.POST, func.HttpMethod.DELETE],
)
async def mcp_endpoint(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """Forward every HTTP method under the function root to the MCP ASGI app."""
    return await func.AsgiMiddleware(_asgi_app).handle_async(req, context)
