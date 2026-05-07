"""AMHCC V1.1 community mental health service-contact NWAU (Table 15).

NWAU = weight_with_consumer if consumer present at contact else
       weight_without_consumer.
"""

from __future__ import annotations

from ..loader import PriceWeightTables


def contact_nwau(
    tables: PriceWeightTables,
    code: str,
    contact_with_consumer: bool = True,
) -> dict:
    row = tables.mh_community.get(code.strip().upper())
    if row is None:
        raise KeyError(f"AMHCC V1.1 community code not found: {code!r}")

    base = (row.weight_with_consumer if contact_with_consumer
            else row.weight_without_consumer) or 0.0

    return {
        "stream": "mh_community",
        "code": row.code,
        "description": row.description,
        "contact_with_consumer": contact_with_consumer,
        "base_nwau": round(base, 6),
    }
