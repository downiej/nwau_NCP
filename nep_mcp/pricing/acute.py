"""AR-DRG V11.0 admitted acute episode NWAU.

IHACPA NEP 2025-26 formula (Table 12):

* Same-day on the same-day payment list and LOS = 0:
      NWAU = w_same_day
* Short-stay outlier (LOS < lower_bound):
      NWAU = w_sso_base + LOS * w_sso_per_diem
* Inlier (lower_bound <= LOS <= upper_bound):
      NWAU = w_inlier
* Long-stay outlier (LOS > upper_bound):
      NWAU = w_inlier + (LOS - upper_bound) * w_lso_per_diem

Paediatric adjustment (per-DRG, from the table) multiplies the result when
the patient is paediatric. Cross-cutting demographic uplifts (Indigenous,
remoteness, private) are layered on by the dispatcher.
"""

from __future__ import annotations

from ..adjustments import Demographics
from ..loader import AcuteRow, PriceWeightTables


def _select(row: AcuteRow, los: int) -> tuple[float, str]:
    if los <= 0 and row.same_day_eligible and row.weight_same_day is not None:
        return row.weight_same_day, "same_day"

    los_eff = max(los, 1)
    lower = row.inlier_lower or 0
    upper = row.inlier_upper or 10**9

    if los_eff < lower:
        if row.weight_sso_base is None or row.weight_sso_per_diem is None:
            # Fall back to inlier if SSO weights aren't published for this DRG.
            return row.weight_inlier or 0.0, "inlier"
        return row.weight_sso_base + los_eff * row.weight_sso_per_diem, "sso"

    if los_eff <= upper:
        return row.weight_inlier or 0.0, "inlier"

    inlier = row.weight_inlier or 0.0
    lso_pd = row.weight_lso_per_diem or 0.0
    return inlier + (los_eff - upper) * lso_pd, "lso"


def episode_nwau(
    tables: PriceWeightTables,
    code: str,
    los: int = 0,
    demographics: Demographics | None = None,
) -> dict:
    row = tables.acute.get(code.strip().upper())
    if row is None:
        raise KeyError(f"AR-DRG V11.0 code not found: {code!r}")

    base, payment_class = _select(row, los)

    paed_mult = 1.0
    if demographics and getattr(demographics, "is_paediatric", False):
        paed_mult = row.paediatric_adjustment
    base_nwau = base * paed_mult

    return {
        "stream": "acute",
        "code": row.code,
        "description": row.description,
        "los": los,
        "payment_class": payment_class,
        "inlier_bounds": [row.inlier_lower, row.inlier_upper],
        "alos": row.alos,
        "paediatric_multiplier": paed_mult,
        "base_nwau": round(base_nwau, 6),
    }
