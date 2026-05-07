"""AMHCC V1.1 admitted mental health phase NWAU.

IHACPA NEP 2025-26 formula (Table 14), per phase of care:

* SSO (LOS < lower_bound):  NWAU = w_sso_base + LOS * w_sso_per_diem
* Inlier (LB <= LOS <= UB): NWAU = w_inlier
* LSO  (LOS > UB):          NWAU = w_inlier + (LOS - UB) * w_lso_per_diem
"""

from __future__ import annotations

from ..adjustments import Demographics
from ..loader import MentalHealthAdmittedRow, PriceWeightTables


def _select(row: MentalHealthAdmittedRow, los: int) -> tuple[float, str]:
    los_eff = max(los, 1)
    lower = row.inlier_lower or 0
    upper = row.inlier_upper or 10**9

    if los_eff < lower:
        if row.weight_sso_base is None or row.weight_sso_per_diem is None:
            return row.weight_inlier or 0.0, "inlier"
        return row.weight_sso_base + los_eff * row.weight_sso_per_diem, "sso"

    if los_eff <= upper:
        return row.weight_inlier or 0.0, "inlier"

    inlier = row.weight_inlier or 0.0
    lso_pd = row.weight_lso_per_diem or 0.0
    return inlier + (los_eff - upper) * lso_pd, "lso"


def phase_nwau(
    tables: PriceWeightTables,
    code: str,
    los: int = 0,
    demographics: Demographics | None = None,
) -> dict:
    row = tables.mh_admitted.get(code.strip().upper())
    if row is None:
        raise KeyError(f"AMHCC V1.1 admitted phase code not found: {code!r}")

    base, payment_class = _select(row, los)
    return {
        "stream": "mh_admitted",
        "code": row.code,
        "description": row.description,
        "los": los,
        "payment_class": payment_class,
        "inlier_bounds": [row.inlier_lower, row.inlier_upper],
        "average_phase_length": row.avg_phase_length,
        "base_nwau": round(base, 6),
    }
