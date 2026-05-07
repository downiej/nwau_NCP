"""Apply NEP demographic adjustments to a base NWAU.

The xlsx already encodes per-row paediatric multipliers for AR-DRG and
Tier 2 — those are applied inside each pricing module. This file handles
the cross-cutting demographic uplifts (Indigenous, remoteness, private)
that aren't in the price-weight tables themselves.

Multiplier values live in config.DEMOGRAPHIC_ADJUSTMENTS so they can be
updated each year without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEMOGRAPHIC_ADJUSTMENTS


@dataclass(frozen=True)
class Demographics:
    indigenous: bool = False
    patient_remoteness: str | None = None
    treatment_remoteness: str | None = None
    private_patient_service: bool = False
    private_patient_accommodation: bool = False
    # Per-stream paediatric multipliers live in the price-weight tables (AR-DRG,
    # Tier 2) so this is a flag, not a multiplier — the pricing module looks up
    # the per-row factor when the flag is set.
    is_paediatric: bool = False


def parse_demographics(payload: dict | None) -> Demographics:
    if not payload:
        return Demographics()
    return Demographics(
        indigenous=bool(payload.get("indigenous", False)),
        patient_remoteness=_norm_remoteness(payload.get("patient_remoteness")),
        treatment_remoteness=_norm_remoteness(payload.get("treatment_remoteness")),
        private_patient_service=bool(payload.get("private_patient_service", False)),
        private_patient_accommodation=bool(payload.get("private_patient_accommodation", False)),
        is_paediatric=bool(payload.get("is_paediatric", False)),
    )


def _norm_remoteness(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    valid = set(DEMOGRAPHIC_ADJUSTMENTS.patient_remoteness)
    return s if s in valid else None


def apply(nwau: float, demographics: Demographics | None) -> tuple[float, dict[str, float]]:
    """Return (adjusted_nwau, breakdown) where breakdown maps factor → multiplier."""
    if demographics is None:
        return nwau, {}

    cfg = DEMOGRAPHIC_ADJUSTMENTS
    breakdown: dict[str, float] = {}
    out = nwau

    if demographics.indigenous:
        breakdown["indigenous"] = cfg.indigenous
        out *= cfg.indigenous

    if demographics.patient_remoteness:
        m = cfg.patient_remoteness.get(demographics.patient_remoteness, 1.0)
        if m != 1.0:
            breakdown[f"patient_remoteness:{demographics.patient_remoteness}"] = m
            out *= m

    if demographics.treatment_remoteness:
        m = cfg.treatment_remoteness.get(demographics.treatment_remoteness, 1.0)
        if m != 1.0:
            breakdown[f"treatment_remoteness:{demographics.treatment_remoteness}"] = m
            out *= m

    if demographics.private_patient_service:
        breakdown["private_patient_service"] = cfg.private_patient_service
        out *= cfg.private_patient_service

    if demographics.private_patient_accommodation:
        breakdown["private_patient_accommodation"] = cfg.private_patient_accommodation
        out *= cfg.private_patient_accommodation

    return out, breakdown
