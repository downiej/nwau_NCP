"""Runtime configuration for the NEP MCP server.

All knobs live here so the server is easy to redeploy with a new annual NEP
release: bump NEP_PRICE, swap PRICE_WEIGHTS_PATH to the new xlsx, and review
DEMOGRAPHIC_ADJUSTMENTS against the new determination.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

DEFAULT_XLSX = PROJECT_ROOT / "price_weights" / "nep_2025_26_price_weights.xlsx"


@dataclass(frozen=True)
class Settings:
    nep_price: float
    price_weights_path: Path
    api_key: str | None
    determination_year: str
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    server_name: str = "nep-pricing"


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(s.strip() for s in value.split(",") if s.strip())


def load_settings() -> Settings:
    return Settings(
        nep_price=float(os.environ.get("NEP_PRICE", "7258")),
        price_weights_path=Path(
            os.environ.get("NEP_XLSX_PATH", str(DEFAULT_XLSX))
        ),
        api_key=os.environ.get("NEP_API_KEY") or None,
        determination_year=os.environ.get("NEP_YEAR", "2025-26"),
        # Extra host headers the MCP transport will accept beyond the local
        # defaults (127.0.0.1, localhost, [::1]). Set this to your Azure
        # Functions hostname in production, e.g. "cove-nep-mcp.azurewebsites.net".
        allowed_hosts=_split_csv(os.environ.get("NEP_ALLOWED_HOSTS")),
        allowed_origins=_split_csv(os.environ.get("NEP_ALLOWED_ORIGINS")),
    )


@dataclass(frozen=True)
class DemographicMultipliers:
    """NEP 2025-26 demographic adjustment multipliers.

    Source: IHACPA National Efficient Price Determination 2025-26.
    Verify these annually against the current determination — they drive
    every dollar figure produced by the server.
    """

    indigenous: float = 1.04
    patient_remoteness: dict[str, float] = field(
        default_factory=lambda: {
            "major_city": 1.00,
            "inner_regional": 1.00,
            "outer_regional": 1.00,
            "remote": 1.12,
            "very_remote": 1.25,
        }
    )
    treatment_remoteness: dict[str, float] = field(
        default_factory=lambda: {
            "major_city": 1.00,
            "inner_regional": 1.00,
            "outer_regional": 1.04,
            "remote": 1.18,
            "very_remote": 1.25,
        }
    )
    private_patient_service: float = 0.91
    private_patient_accommodation: float = 0.88


DEMOGRAPHIC_ADJUSTMENTS = DemographicMultipliers()
