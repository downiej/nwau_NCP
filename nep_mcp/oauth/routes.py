"""Extra Starlette route for the Microsoft -> us redirect leg of the broker flow.

FastMCP's auth machinery wires up /authorize, /token, /register and the
well-known endpoints automatically once we hand it an
OAuthAuthorizationServerProvider. The one piece it does NOT know about is
our private callback that Microsoft redirects to after the user signs in.
That route lives here.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .provider import MicrosoftBrokerProvider


log = logging.getLogger(__name__)


def _make_handler(provider: MicrosoftBrokerProvider):
    async def microsoft_callback(request: Request) -> Response:
        params = request.query_params
        if "error" in params:
            return _error_page(params.get("error"), params.get("error_description"))

        code = params.get("code")
        state = params.get("state")
        if not code or not state:
            return _error_page("invalid_request", "Missing code or state in callback")

        try:
            redirect = await provider.complete_microsoft_callback(code, state)
        except Exception as exc:  # noqa: BLE001
            log.exception("Microsoft callback exchange failed")
            return _error_page("server_error", str(exc))

        return RedirectResponse(redirect, status_code=302)

    return microsoft_callback


def _error_page(code: str | None, description: str | None) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<title>Sign-in failed</title>
<style>body{{font-family:system-ui;max-width:540px;margin:4rem auto;padding:0 1rem}}
code{{background:#f3f4f6;padding:.1rem .35rem;border-radius:.25rem}}</style>
<h1>Sign-in didn't complete</h1>
<p>Microsoft returned an error and we couldn't finish setting up the connection.</p>
<p><strong>Code:</strong> <code>{code or "?"}</code></p>
<p><strong>Detail:</strong> {description or "(none provided)"}</p>
<p>Close this tab and try again. If it keeps happening, send the code above to whoever set up the connector.</p>
""",
        status_code=400,
    )


def register_microsoft_callback_route(app, provider: MicrosoftBrokerProvider) -> None:
    """Mount /oauth/microsoft_callback on the Starlette app FastMCP returned."""
    app.routes.append(Route("/oauth/microsoft_callback", _make_handler(provider)))
