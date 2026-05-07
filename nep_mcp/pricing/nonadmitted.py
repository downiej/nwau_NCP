"""Tier 2 V9.1 non-admitted service NWAU (Table 16).

NWAU = w_service * paediatric_adjustment_if_paediatric_else_1.
The paediatric adjustment is per-row in the table.
"""

from __future__ import annotations

from ..loader import PriceWeightTables


def _normalise_code(code: str) -> str:
    """Tier 2 codes look like '20.13' or '40.05' — accept ints, floats, strings."""
    s = str(code).strip()
    return s


def service_nwau(
    tables: PriceWeightTables,
    code: str,
    paediatric: bool = False,
) -> dict:
    key = _normalise_code(code)
    row = tables.non_admitted.get(key)
    if row is None:
        # Try formatting variations: "20.13" vs "20.13" with trailing zero, etc.
        for k in tables.non_admitted:
            if k.rstrip("0").rstrip(".") == key.rstrip("0").rstrip("."):
                row = tables.non_admitted[k]
                break
    if row is None:
        raise KeyError(f"Tier 2 V9.1 code not found: {code!r}")

    paed_mult = row.paediatric_adjustment if paediatric else 1.0
    base = row.weight * paed_mult

    return {
        "stream": "non_admitted",
        "code": row.code,
        "description": row.description,
        "paediatric_multiplier": paed_mult,
        "base_nwau": round(base, 6),
    }
