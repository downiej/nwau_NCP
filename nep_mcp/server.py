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

from .adjustments import parse_demographics
from .config import load_settings
from .loader import iter_classifications
from .pricing import STREAMS, compute_dollars, compute_nwau
from .pricing.subacute import average_daily_rate_by_care_type
from .store import get_settings, get_tables


log = logging.getLogger(__name__)

Stream = Literal[
    "acute",
    "subacute",
    "mh_admitted",
    "mh_community",
    "non_admitted",
    "aecc",
    "udg",
]


mcp = FastMCP("nep-pricing")


def _validate_stream(stream: str) -> str:
    s = stream.strip().lower()
    if s not in STREAMS:
        raise ValueError(
            f"Unknown stream {stream!r}. Must be one of {sorted(STREAMS)}."
        )
    return s


@mcp.tool()
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

    Returns the lookup metadata, base NWAU, demographic-adjusted NWAU, and
    the multipliers applied.
    """
    s = _validate_stream(stream)
    demos = parse_demographics(demographics)
    return compute_nwau(
        get_tables(),
        stream=s,
        code=classification_code,
        los=los,
        demographics=demos,
        contact_with_consumer=contact_with_consumer,
    )


@mcp.tool()
def get_rate_dollars(
    stream: Stream,
    classification_code: str,
    los: int = 0,
    demographics: dict | None = None,
    contact_with_consumer: bool = True,
) -> dict[str, Any]:
    """Same call as get_nwau, but with AUD funding amounts at the configured NEP.

    Returns base_dollars (NWAU * NEP) and adjusted_dollars (after demographics).
    """
    settings = get_settings()
    result = get_nwau(
        stream=stream,
        classification_code=classification_code,
        los=los,
        demographics=demographics,
        contact_with_consumer=contact_with_consumer,
    )
    result["nep_price_aud"] = settings.nep_price
    result["determination_year"] = settings.determination_year
    result["base_dollars"] = compute_dollars(settings.nep_price, result["base_nwau"])
    result["adjusted_dollars"] = compute_dollars(settings.nep_price, result["adjusted_nwau"])
    return result


@mcp.tool()
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
        return {
            "nep_price_aud": settings.nep_price,
            "determination_year": settings.determination_year,
            "by_care_type": by_care_type,
        }

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
    return {
        "nep_price_aud": settings.nep_price,
        "determination_year": settings.determination_year,
        "care_type": match,
        **by_care_type[match],
    }


@mcp.tool()
def list_classifications(stream: Stream) -> dict[str, Any]:
    """List every classification code in a stream with its description."""
    s = _validate_stream(stream)
    items = [
        {"code": code, "description": desc}
        for code, desc in iter_classifications(get_tables(), s)
    ]
    return {"stream": s, "count": len(items), "classifications": items}


@mcp.tool()
def search_classifications(stream: Stream, query: str) -> dict[str, Any]:
    """Substring search over codes and descriptions in a stream (case-insensitive)."""
    s = _validate_stream(stream)
    q = (query or "").strip().lower()
    if not q:
        return {"stream": s, "query": q, "count": 0, "matches": []}

    matches = [
        {"code": code, "description": desc}
        for code, desc in iter_classifications(get_tables(), s)
        if q in code.lower() or q in (desc or "").lower()
    ]
    return {"stream": s, "query": q, "count": len(matches), "matches": matches}


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
    return mcp.streamable_http_app()
