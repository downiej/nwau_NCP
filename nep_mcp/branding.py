"""Markdown render layer that wraps every tool result with Cove branding.

Each tool keeps returning its full structured dict — we just attach a
``display_markdown`` field that Claude is instructed (in the tool docstring)
to use as the primary user-facing answer. Falls back to JSON in clients that
ignore the field.

Brand voice: minimal, professional, factual. No emoji, no decorative borders
beyond a single rule. Source attribution and determination year always
visible so funding figures can be traced.
"""

from __future__ import annotations

from typing import Any


COVE_HEADER = "**Cove Solutions** · NEP Pricing"
RULE = "─" * 48
SOURCE_LINE = "_Source: IHACPA National Efficient Price Determination 2025-26 · Cove Solutions_"


def _aud(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _bounds(bounds: list | None) -> str:
    if not bounds or len(bounds) != 2 or bounds[0] is None:
        return "—"
    return f"{bounds[0]}–{bounds[1]} days"


def _multipliers(mults: dict | None) -> str:
    if not mults:
        return "(none)"
    return ", ".join(f"{k} × {v:g}" for k, v in mults.items())


def episode(result: dict[str, Any]) -> str:
    """Markdown card for get_nwau / get_rate_dollars (acute, subacute, MH admitted)."""
    code = result.get("code", "?")
    desc = result.get("description", "")
    los = result.get("los")
    payment = result.get("payment_class", "")
    bounds = result.get("inlier_bounds")
    alos = result.get("alos") or result.get("average_phase_length")

    rows = [
        f"| Base NWAU | {result.get('base_nwau', 0):.4f} |",
    ]
    if "paediatric_multiplier" in result and result["paediatric_multiplier"] != 1.0:
        rows.append(f"| Paediatric multiplier | × {result['paediatric_multiplier']:g} |")

    mults = result.get("demographic_multipliers", {})
    rows.append(f"| Demographic multipliers | {_multipliers(mults)} |")
    if "adjusted_nwau" in result and result["adjusted_nwau"] != result.get("base_nwau"):
        rows.append(f"| Adjusted NWAU | {result['adjusted_nwau']:.4f} |")

    if "base_dollars" in result:
        if result.get("adjusted_dollars") != result.get("base_dollars"):
            rows.append(f"| Base funding (AUD) | {_aud(result['base_dollars'])} |")
            rows.append(f"| **Total funding (AUD)** | **{_aud(result['adjusted_dollars'])}** |")
        else:
            rows.append(f"| **Total funding (AUD)** | **{_aud(result['base_dollars'])}** |")

    los_line = ""
    if los is not None:
        los_line = f"Length of stay: **{los} days** · "
    payment_line = f"Payment class: **{payment}**" if payment else ""
    band_line = ""
    if bounds and bounds[0] is not None:
        band_line = f" (band {_bounds(bounds)}"
        if alos:
            band_line += f", ALOS {alos}"
        band_line += ")"

    return "\n".join([
        COVE_HEADER,
        RULE,
        f"**{code}** — {desc}".rstrip(" —"),
        f"{los_line}{payment_line}{band_line}".strip(),
        "",
        "| Metric | Value |",
        "|---|---|",
        *rows,
        "",
        SOURCE_LINE,
    ])


def community_contact(result: dict[str, Any]) -> str:
    """Markdown for AMHCC community contact (mh_community)."""
    code = result.get("code", "?")
    desc = result.get("description", "")
    with_consumer = result.get("contact_with_consumer")
    contact_line = "with consumer present" if with_consumer else "without consumer"
    rows = [
        f"| Contact type | {contact_line} |",
        f"| Base NWAU | {result.get('base_nwau', 0):.4f} |",
    ]
    if "demographic_multipliers" in result:
        rows.append(f"| Demographic multipliers | {_multipliers(result['demographic_multipliers'])} |")
    if "adjusted_nwau" in result and result["adjusted_nwau"] != result.get("base_nwau"):
        rows.append(f"| Adjusted NWAU | {result['adjusted_nwau']:.4f} |")
    if "base_dollars" in result:
        rows.append(f"| **Funding per contact (AUD)** | **{_aud(result.get('adjusted_dollars', result['base_dollars']))}** |")

    return "\n".join([
        COVE_HEADER,
        RULE,
        f"**{code}** — {desc}".rstrip(" —"),
        "",
        "| Metric | Value |",
        "|---|---|",
        *rows,
        "",
        SOURCE_LINE,
    ])


def average_daily_rate(result: dict[str, Any]) -> str:
    """Markdown for get_average_daily_rate (single care_type or all)."""
    nep = result.get("nep_price_aud", 0)
    year = result.get("determination_year", "")

    if "care_type" in result:
        return "\n".join([
            COVE_HEADER,
            RULE,
            f"**Average daily rate — {result['care_type']}**",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Average daily rate | **{_aud(result.get('average_daily_rate_aud'))}** per day |",
            f"| Range across classifications | {_aud(result.get('min_aud'))} – {_aud(result.get('max_aud'))} |",
            f"| Classifications averaged | {result.get('n_classifications', '—')} |",
            f"| NEP price | {_aud(nep)} per NWAU ({year}) |",
            "",
            SOURCE_LINE,
        ])

    by_ct = result.get("by_care_type", {})
    rows = [
        f"| {ct} | **{_aud(s['average_daily_rate_aud'])}** | {_aud(s['min_aud'])} – {_aud(s['max_aud'])} | {s['n_classifications']} |"
        for ct, s in sorted(by_ct.items())
    ]
    return "\n".join([
        COVE_HEADER,
        RULE,
        f"**Subacute average daily rates** · NEP {year} · {_aud(nep)} per NWAU",
        "",
        "| Care type | Avg daily rate | Range | n |",
        "|---|---|---|---|",
        *rows,
        "",
        SOURCE_LINE,
    ])


_STREAM_LABEL = {
    "acute": "AR-DRG V11.0 Admitted Acute",
    "subacute": "AN-SNAP V5.0 Admitted Subacute",
    "mh_admitted": "AMHCC V1.1 Admitted Mental Health",
    "mh_community": "AMHCC V1.1 Community Mental Health",
    "non_admitted": "Tier 2 V9.1 Non-Admitted",
    "aecc": "AECC V1.1 Emergency",
    "udg": "UDG V1.3 Emergency Service",
}


def classifications_summary(stream: str, count: int, items: list[dict]) -> str:
    """Markdown summary for list_classifications (truncated preview)."""
    label = _STREAM_LABEL.get(stream, stream)
    preview_n = 10
    rows = [f"- `{i['code']}` — {i['description']}" for i in items[:preview_n]]
    more = ""
    if count > preview_n:
        more = f"\n\n_Showing first {preview_n} of {count}. The full list is in the JSON payload._"

    return "\n".join([
        COVE_HEADER,
        RULE,
        f"**{label}** — {count} classifications",
        "",
        *rows,
        more,
        "",
        SOURCE_LINE,
    ])


def search_results(stream: str, query: str, matches: list[dict]) -> str:
    """Markdown summary for search_classifications."""
    label = _STREAM_LABEL.get(stream, stream)
    if not matches:
        return "\n".join([
            COVE_HEADER,
            RULE,
            f"No matches in {label} for `{query}`",
            "",
            SOURCE_LINE,
        ])

    preview_n = 15
    rows = [f"- `{m['code']}` — {m['description']}" for m in matches[:preview_n]]
    more = ""
    if len(matches) > preview_n:
        more = f"\n\n_Showing first {preview_n} of {len(matches)}._"

    return "\n".join([
        COVE_HEADER,
        RULE,
        f"**{label}** — {len(matches)} match{'es' if len(matches) != 1 else ''} for `{query}`",
        "",
        *rows,
        more,
        "",
        SOURCE_LINE,
    ])
