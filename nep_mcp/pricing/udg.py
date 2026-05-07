"""UDG V1.3 emergency service presentation NWAU (Table 18).

NWAU = w_presentation. No LOS adjustment.
"""

from __future__ import annotations

from ..loader import PriceWeightTables


def presentation_nwau(tables: PriceWeightTables, code: str) -> dict:
    row = tables.udg.get(code.strip().upper())
    if row is None:
        raise KeyError(f"UDG V1.3 code not found: {code!r}")
    return {
        "stream": "udg",
        "code": row.code,
        "description": row.description,
        "base_nwau": round(row.weight, 6),
    }
