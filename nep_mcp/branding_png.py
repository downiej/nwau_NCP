"""PNG card renderer — the bulletproof branding fallback.

Whatever the client does with our HTML resource block, it renders an
``ImageContent`` verbatim. So if Claude won't honour the MCP UI extension,
the PNG ensures the Cove brand still lands.

Layout target: 680 × 360 px, navy header + body + grey footer. Mirrors
``branding_html`` but drawn with Pillow primitives. System font fallbacks
cover Azure Functions Linux (DejaVu), Windows (Segoe UI / Arial), and macOS.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont


COVE_NAVY = (26, 46, 84)
COVE_TEAL = (63, 168, 163)
COVE_CREAM = (239, 225, 168)
COVE_GREY = (245, 245, 245)
COVE_MUTED = (107, 117, 133)
COVE_BORDER = (224, 230, 237)
COVE_NAVY_TEXT = COVE_NAVY
WHITE = (255, 255, 255)


_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

# Search in order; first match wins per platform.
_FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",        # Azure Linux
    "C:/Windows/Fonts/segoeui.ttf",                            # Windows
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",                     # macOS
]
_FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_PATHS_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
    "C:/Windows/Fonts/cour.ttf",
]


def _font(size: int, bold: bool = False, mono: bool = False):
    key = (size, bold, mono)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    paths = _FONT_PATHS_MONO if mono else (_FONT_PATHS_BOLD if bold else _FONT_PATHS_REGULAR)
    for p in paths:
        try:
            f = ImageFont.truetype(p, size)
            _FONT_CACHE[key] = f
            return f
        except (OSError, IOError):
            continue
    # Last resort
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _text_width(d: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = d.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _aud(value) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# --------------------------------------------------------- Card scaffolding
HEADER_H = 50
FOOTER_H = 32
PAD_X = 22

SOURCE = "Source: IHACPA NEP Determination 2025-26 · Computed by Cove Solutions"


def _draw_card_chrome(W: int, H: int, header_label: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Draws the navy header band and grey footer; returns canvas + draw."""
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    # Outer border
    d.rectangle([(0, 0), (W - 1, H - 1)], outline=COVE_BORDER, width=1)

    # Header
    d.rectangle([(1, 1), (W - 2, HEADER_H)], fill=COVE_NAVY)

    # Brand mark (a small teal/cream/grey block as a logo-ish glyph)
    mark_x, mark_y, mark_w, mark_h = PAD_X - 4, 12, 24, 28
    d.rectangle([(mark_x, mark_y), (mark_x + mark_w, mark_y + mark_h)], fill=WHITE)
    d.rectangle([(mark_x + 2, mark_y + 2), (mark_x + mark_w // 3, mark_y + mark_h - 2)], fill=COVE_TEAL)
    d.rectangle([(mark_x + mark_w // 3, mark_y + 2), (mark_x + 2 * mark_w // 3, mark_y + mark_h - 2)], fill=COVE_CREAM)
    d.rectangle([(mark_x + 2 * mark_w // 3, mark_y + 2), (mark_x + mark_w - 2, mark_y + mark_h - 2)], fill=(200, 205, 215))
    d.rectangle([(mark_x, mark_y), (mark_x + mark_w, mark_y + mark_h)], outline=COVE_NAVY, width=2)

    brand_x = mark_x + mark_w + 10
    d.text((brand_x, 18), "COVE SOLUTIONS", font=_font(13, bold=True), fill=WHITE)

    # Header label (right-aligned)
    label_font = _font(11)
    label_w = _text_width(d, header_label, label_font)
    d.text((W - PAD_X - label_w, 20), header_label, font=label_font, fill=COVE_CREAM)

    # Footer
    d.rectangle([(1, H - FOOTER_H), (W - 2, H - 1)], fill=COVE_GREY)
    d.line([(1, H - FOOTER_H), (W - 2, H - FOOTER_H)], fill=COVE_BORDER, width=1)
    d.text((PAD_X - 4, H - FOOTER_H + 11), SOURCE, font=_font(10), fill=COVE_MUTED)

    return img, d


def _png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_code_chip(d: ImageDraw.ImageDraw, x: int, y: int, code: str) -> int:
    """Draw a teal pill containing the classification code; return new x cursor."""
    f = _font(13, mono=True)
    text_w = _text_width(d, code, f)
    pad_x, pad_y = 8, 4
    chip_w = text_w + pad_x * 2
    chip_h = 22
    d.rounded_rectangle([(x, y), (x + chip_w, y + chip_h)], radius=4, fill=COVE_TEAL)
    d.text((x + pad_x, y + pad_y - 1), code, font=f, fill=WHITE)
    return x + chip_w + 8


def _draw_table(d: ImageDraw.ImageDraw, x: int, y: int, W: int,
                rows: list[tuple[str, str, bool]]) -> int:
    """Two-column key/value table. rows = [(label, value, emphasis_bool)]."""
    label_f = _font(10, bold=True)
    value_f = _font(13)
    value_emph_f = _font(14, bold=True)
    row_h = 28

    for i, (label, value, emph) in enumerate(rows):
        ry = y + i * row_h
        if i > 0:
            d.line([(x, ry), (W - PAD_X, ry)], fill=(238, 241, 245), width=1)
        d.text((x, ry + 7), label.upper(), font=label_f, fill=COVE_MUTED)
        vf = value_emph_f if emph else value_f
        vc = COVE_NAVY if emph else (40, 50, 70)
        d.text((x + 220, ry + 6), value, font=vf, fill=vc)

    return y + len(rows) * row_h


# --------------------------------------------------------- Episode / phase
def render_episode(result: dict[str, Any]) -> bytes:
    code = str(result.get("code", "?"))
    desc = str(result.get("description", ""))
    los = result.get("los")
    payment = str(result.get("payment_class", ""))
    bounds = result.get("inlier_bounds") or [None, None]
    alos = result.get("alos") or result.get("average_phase_length")

    has_dollars = "base_dollars" in result
    hero_value = (
        _aud(result.get("adjusted_dollars", result.get("base_dollars")))
        if has_dollars else f"{result.get('adjusted_nwau', result.get('base_nwau', 0)):.4f} NWAU"
    )
    hero_secondary = f"{result.get('adjusted_nwau', 0):.4f} NWAU" if has_dollars else ""

    rows: list[tuple[str, str, bool]] = []
    if los is not None:
        rows.append(("Length of stay", f"{los} days", False))
    if payment:
        rows.append(("Payment class", payment, False))
    if bounds[0] is not None:
        band = f"{bounds[0]}–{bounds[1]} days"
        if alos:
            band += f" (ALOS {alos})"
        rows.append(("Inlier band", band, False))

    mults = result.get("demographic_multipliers") or {}
    if mults:
        mult_str = _truncate(", ".join(f"{k} × {v:g}" for k, v in mults.items()), 50)
        rows.append(("Demographic uplifts", mult_str, False))

    rows.append(("Base NWAU", f"{result.get('base_nwau', 0):.4f}", False))
    if has_dollars and result.get("adjusted_dollars") != result.get("base_dollars"):
        rows.append(("Base funding", _aud(result.get("base_dollars")), False))
    if has_dollars:
        rows.append(("NEP price", f"{_aud(result.get('nep_price_aud'))} per NWAU", False))

    # Dynamic height based on row count
    H = HEADER_H + 130 + len(rows) * 28 + FOOTER_H + 16
    W = 680
    year = result.get("determination_year", "2025-26")
    stream = str(result.get("stream", "")).replace("_", " ").title()
    img, d = _draw_card_chrome(W, H, f"NEP {year} · {stream}")

    # Hero number
    hero_f = _font(34, bold=True)
    d.text((PAD_X, HEADER_H + 18), hero_value, font=hero_f, fill=COVE_NAVY)
    if hero_secondary:
        hw = _text_width(d, hero_value, hero_f)
        d.text((PAD_X + hw + 12, HEADER_H + 32), hero_secondary,
               font=_font(15), fill=COVE_MUTED)

    # Code chip + description
    chip_y = HEADER_H + 70
    cursor_x = _draw_code_chip(d, PAD_X, chip_y, code)
    desc_truncated = _truncate(desc, 60)
    d.text((cursor_x, chip_y + 3), desc_truncated, font=_font(13), fill=(40, 50, 70))

    # Table
    _draw_table(d, PAD_X, HEADER_H + 110, W, rows)

    return _png_bytes(img)


# --------------------------------------------------------- Community contact
def render_community_contact(result: dict[str, Any]) -> bytes:
    code = str(result.get("code", "?"))
    desc = str(result.get("description", ""))
    with_consumer = result.get("contact_with_consumer")
    contact_label = "with consumer present" if with_consumer else "without consumer"

    has_dollars = "base_dollars" in result
    hero = (
        _aud(result.get("adjusted_dollars", result.get("base_dollars")))
        if has_dollars else f"{result.get('base_nwau', 0):.4f} NWAU"
    )

    rows = [
        ("Contact type", contact_label, False),
        ("Base NWAU", f"{result.get('base_nwau', 0):.4f}", False),
    ]
    if has_dollars:
        rows.append(("NEP price", f"{_aud(result.get('nep_price_aud'))} per NWAU", False))

    H = HEADER_H + 130 + len(rows) * 28 + FOOTER_H + 16
    W = 680
    year = result.get("determination_year", "2025-26")
    img, d = _draw_card_chrome(W, H, f"NEP {year} · Community Mental Health")

    hero_f = _font(34, bold=True)
    d.text((PAD_X, HEADER_H + 18), hero, font=hero_f, fill=COVE_NAVY)
    hw = _text_width(d, hero, hero_f)
    d.text((PAD_X + hw + 12, HEADER_H + 32), "per contact",
           font=_font(15), fill=COVE_MUTED)

    chip_y = HEADER_H + 70
    cursor_x = _draw_code_chip(d, PAD_X, chip_y, code)
    d.text((cursor_x, chip_y + 3), _truncate(desc, 60), font=_font(13), fill=(40, 50, 70))

    _draw_table(d, PAD_X, HEADER_H + 110, W, rows)
    return _png_bytes(img)


# --------------------------------------------------------- Average daily rate
def render_average_daily_rate(result: dict[str, Any]) -> bytes:
    nep = result.get("nep_price_aud")
    year = result.get("determination_year", "2025-26")
    W = 680

    if "care_type" in result:
        rows = [
            ("Range across classes", f"{_aud(result.get('min_aud'))} – {_aud(result.get('max_aud'))}", False),
            ("Classes averaged", str(result.get("n_classifications", "—")), False),
            ("NEP price", f"{_aud(nep)} per NWAU", False),
        ]
        H = HEADER_H + 130 + len(rows) * 28 + FOOTER_H + 16
        img, d = _draw_card_chrome(W, H, f"NEP {year} · Subacute · {result.get('care_type')}")
        d.text((PAD_X, HEADER_H + 18), _aud(result.get("average_daily_rate_aud")),
               font=_font(34, bold=True), fill=COVE_NAVY)
        hw = _text_width(d, _aud(result.get("average_daily_rate_aud")), _font(34, bold=True))
        d.text((PAD_X + hw + 12, HEADER_H + 32), "per day",
               font=_font(15), fill=COVE_MUTED)
        d.text((PAD_X, HEADER_H + 70), f"{result.get('care_type')} (AN-SNAP V5.0)",
               font=_font(14), fill=COVE_MUTED)
        _draw_table(d, PAD_X, HEADER_H + 110, W, rows)
        return _png_bytes(img)

    # All care types — table layout
    by_ct = result.get("by_care_type", {})
    sorted_items = sorted(by_ct.items())
    H = HEADER_H + 100 + len(sorted_items) * 30 + FOOTER_H + 16
    img, d = _draw_card_chrome(W, H, f"NEP {year} · Subacute Daily Rates")

    d.text((PAD_X, HEADER_H + 18), "Subacute average daily rates",
           font=_font(22, bold=True), fill=COVE_NAVY)
    d.text((PAD_X, HEADER_H + 50), f"AN-SNAP V5.0 · {_aud(nep)} per NWAU",
           font=_font(13), fill=COVE_MUTED)

    # Column headers
    y = HEADER_H + 80
    for x, label in [(PAD_X, "CARE TYPE"), (260, "AVG / DAY"), (380, "RANGE"), (610, "N")]:
        d.text((x, y), label, font=_font(10, bold=True), fill=COVE_MUTED)
    d.line([(PAD_X, y + 16), (W - PAD_X, y + 16)], fill=COVE_BORDER, width=1)

    for i, (ct, s) in enumerate(sorted_items):
        ry = y + 22 + i * 26
        d.text((PAD_X, ry), ct, font=_font(13), fill=(40, 50, 70))
        d.text((260, ry - 1), _aud(s["average_daily_rate_aud"]), font=_font(14, bold=True), fill=COVE_NAVY)
        d.text((380, ry), f"{_aud(s['min_aud'])} – {_aud(s['max_aud'])}",
               font=_font(12), fill=COVE_MUTED)
        d.text((610, ry), str(s["n_classifications"]), font=_font(13), fill=(40, 50, 70))
        if i < len(sorted_items) - 1:
            d.line([(PAD_X, ry + 19), (W - PAD_X, ry + 19)], fill=(238, 241, 245), width=1)

    return _png_bytes(img)


# --------------------------------------------------------- List / search
_STREAM_LABEL = {
    "acute": "AR-DRG V11.0 Admitted Acute",
    "subacute": "AN-SNAP V5.0 Admitted Subacute",
    "mh_admitted": "AMHCC V1.1 Admitted Mental Health",
    "mh_community": "AMHCC V1.1 Community Mental Health",
    "non_admitted": "Tier 2 V9.1 Non-Admitted",
    "aecc": "AECC V1.1 Emergency",
    "udg": "UDG V1.3 Emergency Service",
}


def render_classifications_summary(stream: str, count: int, items: list[dict]) -> bytes:
    label = _STREAM_LABEL.get(stream, stream)
    preview = items[:10]
    W = 680
    H = HEADER_H + 100 + len(preview) * 24 + (24 if count > 10 else 0) + FOOTER_H + 16
    img, d = _draw_card_chrome(W, H, f"NEP 2025-26 · {label}")

    d.text((PAD_X, HEADER_H + 18), str(count), font=_font(34, bold=True), fill=COVE_NAVY)
    cw = _text_width(d, str(count), _font(34, bold=True))
    d.text((PAD_X + cw + 10, HEADER_H + 32), "classifications",
           font=_font(15), fill=COVE_MUTED)
    d.text((PAD_X, HEADER_H + 72), label, font=_font(13), fill=COVE_MUTED)

    y = HEADER_H + 100
    for i, item in enumerate(preview):
        ry = y + i * 24
        chip_end = _draw_code_chip(d, PAD_X, ry - 2, item["code"])
        d.text((chip_end, ry + 1), _truncate(item.get("description", ""), 65),
               font=_font(12), fill=(40, 50, 70))

    if count > 10:
        d.text((PAD_X, y + len(preview) * 24 + 4),
               f"Showing 10 of {count}. Full list in the JSON payload.",
               font=_font(11), fill=COVE_MUTED)

    return _png_bytes(img)


def render_search_results(stream: str, query: str, matches: list[dict]) -> bytes:
    label = _STREAM_LABEL.get(stream, stream)
    W = 680

    if not matches:
        H = HEADER_H + 100 + FOOTER_H + 16
        img, d = _draw_card_chrome(W, H, f"Search · {label}")
        d.text((PAD_X, HEADER_H + 18), "No matches", font=_font(28, bold=True), fill=COVE_NAVY)
        d.text((PAD_X, HEADER_H + 60),
               f'No {label} classifications match "{_truncate(query, 40)}".',
               font=_font(13), fill=COVE_MUTED)
        return _png_bytes(img)

    preview = matches[:12]
    extra_h = 24 if len(matches) > 12 else 0
    H = HEADER_H + 100 + len(preview) * 24 + extra_h + FOOTER_H + 16
    img, d = _draw_card_chrome(W, H, f"Search · {label}")

    count_str = str(len(matches))
    d.text((PAD_X, HEADER_H + 18), count_str, font=_font(34, bold=True), fill=COVE_NAVY)
    cw = _text_width(d, count_str, _font(34, bold=True))
    suffix = "matches" if len(matches) != 1 else "match"
    d.text((PAD_X + cw + 10, HEADER_H + 32),
           f'{suffix} for "{_truncate(query, 30)}"',
           font=_font(15), fill=COVE_MUTED)
    d.text((PAD_X, HEADER_H + 72), label, font=_font(13), fill=COVE_MUTED)

    y = HEADER_H + 100
    for i, m in enumerate(preview):
        ry = y + i * 24
        chip_end = _draw_code_chip(d, PAD_X, ry - 2, m["code"])
        d.text((chip_end, ry + 1), _truncate(m.get("description", ""), 65),
               font=_font(12), fill=(40, 50, 70))

    if len(matches) > 12:
        d.text((PAD_X, y + len(preview) * 24 + 4),
               f"Showing 12 of {len(matches)}.",
               font=_font(11), fill=COVE_MUTED)

    return _png_bytes(img)
