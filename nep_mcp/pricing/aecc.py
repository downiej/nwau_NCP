"""AECC V1.1 emergency department presentation NWAU (Table 17).

NWAU = w_presentation. No LOS adjustment.
"""

from __future__ import annotations

from ..loader import PriceWeightTables


def presentation_nwau(tables: PriceWeightTables, code: str) -> dict:
    row = tables.aecc.get(code.strip().upper())
    if row is None:
        raise KeyError(f"AECC V1.1 code not found: {code!r}")
    return {
        "stream": "aecc",
        "code": row.code,
        "description": row.description,
        "base_nwau": round(row.weight, 6),
    }
