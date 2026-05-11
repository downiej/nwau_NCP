"""HTML cards for the MCP UI extension (`text/html;profile=mcp-app`).

Claude renders content with this MIME type inside a sandboxed iframe, so
the styling here cannot be paraphrased away the way markdown can. That's
the whole reason for level C — markdown alone isn't tamper-proof.

Brand palette taken from the Cove Solutions logo:
    navy   #1a2e54  - primary text + header band
    teal   #3fa8a3  - accent (code chip, primary actions)
    cream  #efe1a8  - header sub-label
    grey   #f5f5f5  - footer band
"""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any


_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "cove_logo.jpg"
_LOGO_DATA_URI: str | None = None


def _logo_data_uri() -> str:
    global _LOGO_DATA_URI
    if _LOGO_DATA_URI is None and _LOGO_PATH.exists():
        b = _LOGO_PATH.read_bytes()
        _LOGO_DATA_URI = f"data:image/jpeg;base64,{base64.b64encode(b).decode('ascii')}"
    return _LOGO_DATA_URI or ""


COVE_NAVY = "#1a2e54"
COVE_TEAL = "#3fa8a3"
COVE_CREAM = "#efe1a8"
COVE_GREY = "#f5f5f5"
COVE_MUTED = "#6b7585"
COVE_BORDER = "#e0e6ed"

_BASE_STYLE = f"""
  :root {{
    --cove-navy: {COVE_NAVY};
    --cove-teal: {COVE_TEAL};
    --cove-cream: {COVE_CREAM};
    --cove-grey: {COVE_GREY};
    --cove-muted: {COVE_MUTED};
    --cove-border: {COVE_BORDER};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Aptos', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    color: var(--cove-navy);
    background: transparent;
  }}
  .card {{
    border: 1px solid var(--cove-border);
    border-radius: 10px;
    overflow: hidden;
    max-width: 680px;
    background: white;
  }}
  .header {{
    background: white;
    color: var(--cove-navy);
    padding: 14px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 3px solid var(--cove-teal);
  }}
  .brand-logo {{ height: 44px; width: auto; display: block; }}
  .header-label {{ font-size: 12px; color: var(--cove-muted); font-weight: 500; }}
  .body {{ padding: 22px 22px 18px; }}
  .hero {{ font-size: 34px; font-weight: 700; color: var(--cove-navy); margin: 0 0 4px; line-height: 1.1; }}
  .hero-secondary {{ font-size: 18px; font-weight: 500; color: var(--cove-muted); margin-left: 10px; }}
  .subhero {{ color: var(--cove-muted); margin: 0 0 18px; font-size: 14px; line-height: 1.4; }}
  .code-chip {{
    display: inline-block;
    background: var(--cove-teal);
    color: white;
    padding: 2px 9px;
    border-radius: 4px;
    font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
    font-size: 13px;
    font-weight: 600;
    margin-right: 8px;
    vertical-align: middle;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ text-align: left; padding: 8px 0; border-bottom: 1px solid #eef1f5; }}
  th {{
    color: var(--cove-muted);
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    width: 40%;
  }}
  td {{ font-weight: 500; }}
  td.value {{ font-weight: 600; }}
  td.emphasis {{ color: var(--cove-navy); font-weight: 700; }}
  tr:last-child th, tr:last-child td {{ border-bottom: none; }}
  ul.codes {{ margin: 0; padding: 0; list-style: none; }}
  ul.codes li {{ padding: 6px 0; border-bottom: 1px solid #eef1f5; font-size: 14px; }}
  ul.codes li:last-child {{ border-bottom: none; }}
  ul.codes code {{
    color: var(--cove-teal);
    font-weight: 600;
    margin-right: 8px;
    font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  }}
  .footer {{
    background: var(--cove-grey);
    padding: 10px 20px;
    font-size: 11px;
    color: var(--cove-muted);
    border-top: 1px solid var(--cove-border);
  }}
"""


def _shell(title: str, body_html: str, footer: str | None = None) -> str:
    footer_html = (
        f'<div class="footer">{html.escape(footer)}</div>' if footer else ""
    )
    logo_uri = _logo_data_uri()
    logo_html = (
        f'<img class="brand-logo" src="{logo_uri}" alt="Cove Solutions">'
        if logo_uri else '<div style="font-weight:700;color:var(--cove-navy);letter-spacing:.08em">COVE SOLUTIONS</div>'
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{_BASE_STYLE}</style></head>
<body><div class="card">
<div class="header">
  {logo_html}
  <div class="header-label">{html.escape(title)}</div>
</div>
<div class="body">{body_html}</div>
{footer_html}
</div></body></html>"""


def _aud(value) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else "—"


SOURCE = "Source: IHACPA National Efficient Price Determination 2025-26 · Computed by Cove Solutions"


# --------------------------------------------------------- episode / phase
def episode(result: dict[str, Any]) -> str:
    code = _esc(result.get("code", "?"))
    desc = _esc(result.get("description", ""))
    los = result.get("los")
    payment = _esc(result.get("payment_class", ""))
    bounds = result.get("inlier_bounds") or [None, None]
    alos = result.get("alos") or result.get("average_phase_length")

    has_dollars = "base_dollars" in result
    hero_value = (
        _aud(result.get("adjusted_dollars", result.get("base_dollars")))
        if has_dollars else f'{result.get("adjusted_nwau", result.get("base_nwau", 0)):.4f} NWAU'
    )
    sub_value = (
        f'{result.get("adjusted_nwau", 0):.4f} NWAU'
        if has_dollars else ""
    )

    rows: list[str] = []
    if los is not None:
        rows.append(f"<tr><th>Length of stay</th><td class='value'>{_esc(los)} days</td></tr>")
    if payment:
        rows.append(f"<tr><th>Payment class</th><td class='value'>{payment}</td></tr>")
    if bounds[0] is not None:
        band_str = f"{bounds[0]}–{bounds[1]} days"
        if alos:
            band_str += f" (ALOS {alos})"
        rows.append(f"<tr><th>Inlier band</th><td>{band_str}</td></tr>")
    if "paediatric_multiplier" in result and result["paediatric_multiplier"] != 1.0:
        rows.append(f"<tr><th>Paediatric uplift</th><td>× {result['paediatric_multiplier']:g}</td></tr>")

    mults = result.get("demographic_multipliers") or {}
    if mults:
        mult_str = ", ".join(f"{_esc(k)} × {v:g}" for k, v in mults.items())
        rows.append(f"<tr><th>Demographic uplifts</th><td>{mult_str}</td></tr>")
    rows.append(f"<tr><th>Base NWAU</th><td>{result.get('base_nwau', 0):.4f}</td></tr>")
    if has_dollars and result.get("adjusted_dollars") != result.get("base_dollars"):
        rows.append(
            f"<tr><th>Base funding</th><td>{_aud(result.get('base_dollars'))}</td></tr>"
        )
    if has_dollars:
        rows.append(
            f"<tr><th>NEP price</th><td>{_aud(result.get('nep_price_aud'))} per NWAU</td></tr>"
        )

    body = f"""
      <p class="hero">{hero_value}<span class="hero-secondary">{sub_value}</span></p>
      <p class="subhero"><span class="code-chip">{code}</span>{desc}</p>
      <table>{''.join(rows)}</table>
    """
    title = f"NEP {result.get('determination_year', '2025-26')} · {result.get('stream', '').replace('_', ' ').title()}"
    return _shell(title, body, SOURCE)


# --------------------------------------------------------- community contact
def community_contact(result: dict[str, Any]) -> str:
    code = _esc(result.get("code", "?"))
    desc = _esc(result.get("description", ""))
    with_consumer = result.get("contact_with_consumer")
    contact_label = "with consumer present" if with_consumer else "without consumer"

    has_dollars = "base_dollars" in result
    hero = _aud(result.get("adjusted_dollars", result.get("base_dollars"))) if has_dollars else f'{result.get("base_nwau", 0):.4f} NWAU'

    rows = [
        f"<tr><th>Contact type</th><td class='value'>{contact_label}</td></tr>",
        f"<tr><th>Base NWAU</th><td>{result.get('base_nwau', 0):.4f}</td></tr>",
    ]
    if has_dollars:
        rows.append(f"<tr><th>NEP price</th><td>{_aud(result.get('nep_price_aud'))} per NWAU</td></tr>")

    body = f"""
      <p class="hero">{hero}<span class="hero-secondary">per contact</span></p>
      <p class="subhero"><span class="code-chip">{code}</span>{desc}</p>
      <table>{''.join(rows)}</table>
    """
    return _shell(f"NEP {result.get('determination_year', '2025-26')} · Community Mental Health", body, SOURCE)


# --------------------------------------------------------- average daily rate
def average_daily_rate(result: dict[str, Any]) -> str:
    nep = result.get("nep_price_aud")
    year = result.get("determination_year", "2025-26")

    if "care_type" in result:
        body = f"""
          <p class="hero">{_aud(result.get('average_daily_rate_aud'))}<span class="hero-secondary">per day</span></p>
          <p class="subhero">{_esc(result.get('care_type'))} (AN-SNAP V5.0)</p>
          <table>
            <tr><th>Range across classifications</th><td>{_aud(result.get('min_aud'))} – {_aud(result.get('max_aud'))}</td></tr>
            <tr><th>Classifications averaged</th><td>{_esc(result.get('n_classifications'))}</td></tr>
            <tr><th>NEP price</th><td>{_aud(nep)} per NWAU</td></tr>
          </table>
        """
        return _shell(f"NEP {year} · Subacute · {result.get('care_type')}", body, SOURCE)

    by_ct = result.get("by_care_type", {})
    rows = []
    for ct, s in sorted(by_ct.items()):
        rows.append(
            f"<tr><th>{_esc(ct)}</th>"
            f"<td class='emphasis'>{_aud(s['average_daily_rate_aud'])}</td>"
            f"<td>{_aud(s['min_aud'])} – {_aud(s['max_aud'])}</td>"
            f"<td>{s['n_classifications']}</td></tr>"
        )

    body = f"""
      <p class="hero">Subacute average daily rates</p>
      <p class="subhero">AN-SNAP V5.0 · NEP {year} · {_aud(nep)} per NWAU</p>
      <table>
        <tr><th>Care type</th><th>Avg / day</th><th>Range</th><th>n</th></tr>
        {''.join(rows)}
      </table>
    """
    return _shell(f"NEP {year} · Subacute Daily Rates", body, SOURCE)


# --------------------------------------------------------- list / search
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
    label = _STREAM_LABEL.get(stream, stream)
    preview = items[:12]
    list_html = "".join(
        f"<li><code>{_esc(i['code'])}</code>{_esc(i['description'])}</li>"
        for i in preview
    )
    more = f"<p class='subhero'>Showing 12 of {count}. Full list available in the JSON payload.</p>" if count > 12 else ""

    body = f"""
      <p class="hero">{count}<span class="hero-secondary">classifications</span></p>
      <p class="subhero">{_esc(label)}</p>
      <ul class="codes">{list_html}</ul>
      {more}
    """
    return _shell(f"NEP 2025-26 · {label}", body, SOURCE)


def search_results(stream: str, query: str, matches: list[dict]) -> str:
    label = _STREAM_LABEL.get(stream, stream)
    if not matches:
        body = f"""
          <p class="hero">No matches</p>
          <p class="subhero">No {_esc(label)} classifications match <code>{_esc(query)}</code>.</p>
        """
        return _shell(f"Search · {label}", body, SOURCE)

    preview = matches[:20]
    list_html = "".join(
        f"<li><code>{_esc(m['code'])}</code>{_esc(m['description'])}</li>"
        for m in preview
    )
    more = f"<p class='subhero'>Showing 20 of {len(matches)}.</p>" if len(matches) > 20 else ""

    body = f"""
      <p class="hero">{len(matches)}<span class="hero-secondary">match{'es' if len(matches) != 1 else ''} for "{_esc(query)}"</span></p>
      <p class="subhero">{_esc(label)}</p>
      <ul class="codes">{list_html}</ul>
      {more}
    """
    return _shell(f"Search · {label}", body, SOURCE)
