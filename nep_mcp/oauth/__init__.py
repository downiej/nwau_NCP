"""OAuth broker: this MCP server is its own OAuth 2.1 authorization server,
delegating user authentication to Microsoft Entra ID.

Public surface:
    MicrosoftBrokerProvider  - implements MCP's OAuthAuthorizationServerProvider
    register_microsoft_callback_route(app)  - adds /oauth/microsoft_callback to the
                                               Starlette app returned by FastMCP.
"""

from .provider import MicrosoftBrokerProvider
from .routes import register_microsoft_callback_route

__all__ = ["MicrosoftBrokerProvider", "register_microsoft_callback_route"]
