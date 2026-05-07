"""Pricing dispatcher: stream name → episode NWAU calculator.

The MCP layer only ever calls compute_nwau / compute_dollars. Each per-stream
module knows the rules for its own classification system.
"""

from __future__ import annotations

from typing import Callable

from ..adjustments import Demographics, apply as apply_demographics
from ..loader import PriceWeightTables
from . import acute, aecc, mh_admitted, mh_community, nonadmitted, subacute, udg


STREAMS = {
    "acute",
    "subacute",
    "mh_admitted",
    "mh_community",
    "non_admitted",
    "aecc",
    "udg",
}


def _calculator(stream: str) -> Callable:
    if stream == "acute":
        return acute.episode_nwau
    if stream == "subacute":
        return subacute.episode_nwau
    if stream == "mh_admitted":
        return mh_admitted.phase_nwau
    if stream == "mh_community":
        return mh_community.contact_nwau
    if stream == "non_admitted":
        return nonadmitted.service_nwau
    if stream == "aecc":
        return aecc.presentation_nwau
    if stream == "udg":
        return udg.presentation_nwau
    raise ValueError(
        f"Unknown stream: {stream!r}. Must be one of {sorted(STREAMS)}."
    )


def compute_nwau(
    tables: PriceWeightTables,
    stream: str,
    code: str,
    los: int | None = None,
    demographics: Demographics | None = None,
    contact_with_consumer: bool | None = None,
) -> dict:
    """Look up a classification and return base NWAU + adjusted NWAU + breakdown.

    Returns a dict with: code, description, base_nwau, adjusted_nwau,
    payment_class (e.g. "inlier" / "sso"), and a breakdown of multipliers.
    """
    calc = _calculator(stream)
    if stream == "mh_community":
        result = calc(tables, code, contact_with_consumer=bool(contact_with_consumer))
    elif stream in {"acute", "subacute", "mh_admitted"}:
        result = calc(tables, code, los=int(los or 0), demographics=demographics)
    elif stream == "non_admitted":
        is_paed = bool(demographics and getattr(demographics, "is_paediatric", False))
        # Non-admitted paediatric uplift comes from the per-row column, not the
        # demographics dataclass; expose via a kwarg on the demographics dict.
        result = calc(tables, code, paediatric=is_paed)
    else:
        result = calc(tables, code)

    base_nwau = result["base_nwau"]
    adjusted, multipliers = apply_demographics(base_nwau, demographics)
    result["adjusted_nwau"] = adjusted
    result["demographic_multipliers"] = multipliers
    return result


def compute_dollars(nep_price: float, nwau: float) -> float:
    return round(nwau * nep_price, 2)
