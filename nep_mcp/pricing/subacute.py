"""AN-SNAP V5.0 admitted subacute / non-acute episode NWAU.

IHACPA NEP 2025-26 formula (Table 13):

* Same-day class:
      NWAU = w_same_day  (per same-day visit)
* Multi-day classes
    - SSO (LOS < lower_bound):    NWAU = LOS * w_sso_per_diem
    - Inlier (LB <= LOS <= UB):   NWAU = w_inlier  (episode-level constant)
    - LSO  (LOS > UB):            NWAU = w_inlier + (LOS - UB) * w_lso_per_diem
"""

from __future__ import annotations

from ..adjustments import Demographics
from ..loader import PriceWeightTables, SubacuteRow


def _select(row: SubacuteRow, los: int) -> tuple[float, str]:
    if row.is_same_day_class:
        return row.weight_same_day or 0.0, "same_day"

    los_eff = max(los, 1)
    lower = row.inlier_lower or 0
    upper = row.inlier_upper or 10**9

    if los_eff < lower:
        per_diem = row.weight_sso_per_diem or 0.0
        return los_eff * per_diem, "sso"

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
    row = tables.subacute.get(code.strip().upper())
    if row is None:
        raise KeyError(f"AN-SNAP V5.0 code not found: {code!r}")

    base, payment_class = _select(row, los)
    return {
        "stream": "subacute",
        "code": row.code,
        "description": row.description,
        "care_type": row.care_type,
        "episode_type": row.episode_type,
        "los": los,
        "payment_class": payment_class,
        "inlier_bounds": [row.inlier_lower, row.inlier_upper],
        "alos": row.alos,
        "base_nwau": round(base, 6),
    }


def average_daily_rate_by_care_type(
    tables: PriceWeightTables, nep_price: float
) -> dict[str, dict]:
    """Mean inlier $/day across multi-day classifications, grouped by care type.

    Same-day classes are excluded since they have no LOS. The figure is
    inlier_NWAU * NEP_price / ALOS, averaged over rows in each care type.
    """
    grouped: dict[str, list[float]] = {}
    for row in tables.subacute.values():
        if row.is_same_day_class or row.weight_inlier is None or not row.alos:
            continue
        rate = row.weight_inlier * nep_price / row.alos
        grouped.setdefault(row.care_type, []).append(rate)

    return {
        care_type: {
            "average_daily_rate_aud": round(sum(rates) / len(rates), 2),
            "n_classifications": len(rates),
            "min_aud": round(min(rates), 2),
            "max_aud": round(max(rates), 2),
        }
        for care_type, rates in sorted(grouped.items())
    }
