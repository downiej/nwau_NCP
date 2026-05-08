"""FastMCP server exposing IHPA NEP 2025-26 funding-metric tools.

The data layer (loader.py, store.py) loads the price-weight xlsx once at
cold start. The pricing layer (pricing/) holds the formulas. This file is
just the MCP-shaped surface — adding next year's xlsx should not need to
change anything here.

Tools:
    get_nwau                  - episode/phase/contact/service NWAU for a code
    get_rate_dollars          - same call, returned in AUD at the configured NEP
    get_average_daily_rate    - subacute care-type average $/day
    list_classifications      - codes + descriptions for a stream
    search_classifications    - substring match on code or description
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from pydantic import AnyHttpUrl

import json

from mcp import types

from . import branding, branding_html
from .adjustments import parse_demographics
from .config import load_settings
from .loader import iter_classifications
from .pricing import STREAMS, compute_dollars, compute_nwau
from .pricing.subacute import average_daily_rate_by_care_type
from .store import get_settings, get_tables


log = logging.getLogger(__name__)


def _build_mcp() -> FastMCP:
    """Construct FastMCP, wiring the OAuth broker if configured.

    With OAuth configured, FastMCP automatically:
      - publishes /.well-known/oauth-authorization-server and /.well-known/oauth-protected-resource
      - exposes /authorize, /token, /register
      - requires bearer auth on the MCP endpoint
    """
    settings = load_settings()
    # stateless_http=True: every request is self-contained; no server-side
    # session table. Required on Flex Consumption because consecutive MCP
    # calls (initialize -> tools/list -> tools/call) routinely land on
    # different workers, and per-process session_ids vanish between hops.
    if not settings.oauth.is_configured():
        return FastMCP("Cove · NEP Pricing", stateless_http=True)

    from .oauth import MicrosoftBrokerProvider

    provider = MicrosoftBrokerProvider(settings.oauth)

    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(settings.oauth.issuer_url),
        resource_server_url=AnyHttpUrl(settings.oauth.issuer_url),
        required_scopes=["mcp.access"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp.access"],
            default_scopes=["mcp.access"],
        ),
    )

    # FastMCP uses provider.load_access_token as the token verifier when
    # auth_server_provider is set; passing both is rejected.
    mcp_app = FastMCP(
        "Cove · NEP Pricing",
        auth_server_provider=provider,
        auth=auth_settings,
        stateless_http=True,
    )
    # Stash the provider so build_app() can register the Microsoft callback route.
    mcp_app._nep_oauth_provider = provider  # type: ignore[attr-defined]
    return mcp_app

Stream = Literal[
    "acute",
    "subacute",
    "mh_admitted",
    "mh_community",
    "non_admitted",
    "aecc",
    "udg",
]


# Build the FastMCP instance once at import time. With OAuth env vars set,
# this wires the Microsoft broker; without them, falls back to no-auth (local dev).
mcp = _build_mcp()


def _validate_stream(stream: str) -> str:
    s = stream.strip().lower()
    if s not in STREAMS:
        raise ValueError(
            f"Unknown stream {stream!r}. Must be one of {sorted(STREAMS)}."
        )
    return s


_UI_MIME = "text/html;profile=mcp-app"


def _ui_response(structured: dict, html_card: str, uri: str) -> list:
    """Wrap the structured result + Cove HTML card as MCP content blocks.

    Two blocks: a TextContent of the JSON payload (so Claude can reason about
    the numbers) and an EmbeddedResource carrying HTML with mime
    ``text/html;profile=mcp-app`` (the MCP UI extension Claude renders inline
    as a sandboxed branded card — paraphrase-proof).
    """
    return [
        types.TextContent(type="text", text=json.dumps(structured, default=str)),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=uri,
                mimeType=_UI_MIME,
                text=html_card,
            ),
        ),
    ]


@mcp.tool(structured_output=False)
def get_nwau(
    stream: Stream,
    classification_code: str,
    los: int = 0,
    demographics: dict | None = None,
    contact_with_consumer: bool = True,
) -> dict[str, Any]:
    """Compute the National Weighted Activity Unit (NWAU) for one episode.

    Args:
        stream: One of acute, subacute, mh_admitted, mh_community,
            non_admitted, aecc, udg.
        classification_code: AR-DRG / AN-SNAP / AMHCC / Tier 2 / AECC / UDG code.
        los: Length of stay in days (acute, subacute, mh_admitted only).
        demographics: Optional dict of patient attributes:
            indigenous (bool), patient_remoteness (str: major_city|inner_regional|
            outer_regional|remote|very_remote), treatment_remoteness (same),
            private_patient_service (bool), private_patient_accommodation (bool),
            is_paediatric (bool — uses per-DRG / per-Tier-2 multipliers).
        contact_with_consumer: For mh_community only — was the consumer present
            at the contact? Defaults to True.

    Returns the lookup metadata, base NWAU, demographic-adjusted NWAU, the
    multipliers applied, and a `display_markdown` field. **When showing the
    answer to a user, render `display_markdown` directly** — it carries the
    Cove Solutions branding and is the intended user-facing presentation.
    """
    s = _validate_stream(stream)
    demos = parse_demographics(demographics)
    result = compute_nwau(
        get_tables(),
        stream=s,
        code=classification_code,
        los=los,
        demographics=demos,
        contact_with_consumer=contact_with_consumer,
    )
    if s == "mh_community":
        result["display_markdown"] = branding.community_contact(result)
        html_card = branding_html.community_contact(result)
    else:
        result["display_markdown"] = branding.episode(result)
        html_card = branding_html.episode(result)
    return _ui_response(result, html_card, f"ui://nep-pricing/{s}/{classification_code}")


@mcp.tool(structured_output=False)
def get_rate_dollars(
    stream: Stream,
    classification_code: str,
    los: int = 0,
    demographics: dict | None = None,
    contact_with_consumer: bool = True,
) -> dict[str, Any]:
    """Same call as get_nwau, but with AUD funding amounts at the configured NEP.

    Returns base_dollars (NWAU * NEP), adjusted_dollars (after demographics),
    and a `display_markdown` field. **When showing the answer to a user,
    render `display_markdown` directly** — it carries the Cove Solutions
    branding and is the intended user-facing presentation.
    """
    settings = get_settings()
    s = _validate_stream(stream)
    demos = parse_demographics(demographics)
    result = compute_nwau(
        get_tables(),
        stream=s,
        code=classification_code,
        los=los,
        demographics=demos,
        contact_with_consumer=contact_with_consumer,
    )
    result["nep_price_aud"] = settings.nep_price
    result["determination_year"] = settings.determination_year
    result["base_dollars"] = compute_dollars(settings.nep_price, result["base_nwau"])
    result["adjusted_dollars"] = compute_dollars(settings.nep_price, result["adjusted_nwau"])
    if s == "mh_community":
        result["display_markdown"] = branding.community_contact(result)
        html_card = branding_html.community_contact(result)
    else:
        result["display_markdown"] = branding.episode(result)
        html_card = branding_html.episode(result)
    return _ui_response(result, html_card, f"ui://nep-pricing/{s}/{classification_code}")


@mcp.tool(structured_output=False)
def get_average_daily_rate(care_type: str | None = None) -> dict[str, Any]:
    """Average inlier $/day across AN-SNAP V5.0 subacute classifications.

    Args:
        care_type: Optional filter: one of Rehabilitation, Palliative Care,
            GEM, Psychogeriatric Care, Maintenance. If omitted, returns all.

    Computed as inlier_NWAU * NEP_price / ALOS, averaged unweighted across
    the multi-day classifications in each care type. Same-day classes are
    excluded.
    """
    settings = get_settings()
    tables = get_tables()
    by_care_type = average_daily_rate_by_care_type(tables, settings.nep_price)

    if care_type is None:
        result = {
            "nep_price_aud": settings.nep_price,
            "determination_year": settings.determination_year,
            "by_care_type": by_care_type,
        }
        result["display_markdown"] = branding.average_daily_rate(result)
        return _ui_response(result, branding_html.average_daily_rate(result),
                            "ui://nep-pricing/subacute-daily-rates/all")

    requested = care_type.strip().lower()
    match = next(
        (k for k in by_care_type if k.lower() == requested),
        None,
    )
    if match is None:
        raise KeyError(
            f"Unknown subacute care_type {care_type!r}. "
            f"Known: {sorted(by_care_type)}."
        )
    result = {
        "nep_price_aud": settings.nep_price,
        "determination_year": settings.determination_year,
        "care_type": match,
        **by_care_type[match],
    }
    result["display_markdown"] = branding.average_daily_rate(result)
    return _ui_response(result, branding_html.average_daily_rate(result),
                        f"ui://nep-pricing/subacute-daily-rates/{match}")


@mcp.tool(structured_output=False)
def list_classifications(stream: Stream) -> dict[str, Any]:
    """List every classification code in a stream with its description.

    Returns the full list plus a Cove-branded `display_markdown` preview of
    the first 10 entries. **When showing the answer to a user, render
    `display_markdown` directly.**
    """
    s = _validate_stream(stream)
    items = [
        {"code": code, "description": desc}
        for code, desc in iter_classifications(get_tables(), s)
    ]
    result = {
        "stream": s,
        "count": len(items),
        "classifications": items,
        "display_markdown": branding.classifications_summary(s, len(items), items),
    }
    return _ui_response(result, branding_html.classifications_summary(s, len(items), items),
                        f"ui://nep-pricing/list/{s}")


@mcp.tool(structured_output=False)
def search_classifications(stream: Stream, query: str) -> dict[str, Any]:
    """Substring search over codes and descriptions in a stream (case-insensitive).

    Returns matches plus a Cove-branded `display_markdown` summary. **When
    showing the answer to a user, render `display_markdown` directly.**
    """
    s = _validate_stream(stream)
    q = (query or "").strip().lower()
    if not q:
        result = {"stream": s, "query": q, "count": 0, "matches": []}
        result["display_markdown"] = branding.search_results(s, query or "", [])
        return _ui_response(result, branding_html.search_results(s, query or "", []),
                            f"ui://nep-pricing/search/{s}/empty")

    matches = [
        {"code": code, "description": desc}
        for code, desc in iter_classifications(get_tables(), s)
        if q in code.lower() or q in (desc or "").lower()
    ]
    result = {
        "stream": s,
        "query": q,
        "count": len(matches),
        "matches": matches,
        "display_markdown": branding.search_results(s, query, matches),
    }
    return _ui_response(result, branding_html.search_results(s, query, matches),
                        f"ui://nep-pricing/search/{s}/{q}")


def _eager_load() -> None:
    """Force the xlsx parse on import so cold starts surface errors early."""
    settings = load_settings()
    log.info("Eager-loading NEP %s tables", settings.determination_year)
    get_tables()


def _apply_transport_security() -> None:
    """Extend MCP's allowed-hosts list with values from env vars.

    FastMCP defaults to 127.0.0.1 / localhost / [::1] only — anything else
    (e.g. the *.azurewebsites.net hostname behind Functions) must be added
    explicitly or every request comes back as 421 Misdirected Request.
    """
    settings = load_settings()
    sec = mcp.settings.transport_security
    if settings.allowed_hosts:
        sec.allowed_hosts = list(sec.allowed_hosts) + list(settings.allowed_hosts)
    if settings.allowed_origins:
        sec.allowed_origins = list(sec.allowed_origins) + list(settings.allowed_origins)


def build_app():
    """Return the Starlette ASGI app for HTTP transport (used by Azure Functions)."""
    _eager_load()
    _apply_transport_security()
    app = mcp.streamable_http_app()

    # If OAuth is configured, attach the Microsoft -> us redirect leg.
    provider = getattr(mcp, "_nep_oauth_provider", None)
    if provider is not None:
        from .oauth import register_microsoft_callback_route
        register_microsoft_callback_route(app, provider)
        log.info("OAuth broker active; Microsoft callback registered at /oauth/microsoft_callback")
    else:
        log.warning("OAuth not configured — server is unauthenticated.")

    return app
