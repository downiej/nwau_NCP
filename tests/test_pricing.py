"""Sanity tests for the pricing layer.

These run against the bundled NEP 2025-26 xlsx. They check that the loader
parses each sheet, that representative codes resolve correctly, and that
SSO / inlier / LSO band selection picks the expected payment class.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nep_mcp.adjustments import Demographics
from nep_mcp.loader import load_price_weights
from nep_mcp.pricing import acute, mh_admitted, mh_community, nonadmitted, subacute, aecc, udg


XLSX = Path(__file__).resolve().parent.parent / "price_weights" / "nep_2025_26_price_weights.xlsx"
NEP = 7258.0


@pytest.fixture(scope="module")
def tables():
    return load_price_weights(XLSX)


def test_loader_populates_all_streams(tables):
    assert len(tables.acute) > 700, "AR-DRG V11.0 should have ~800 rows"
    assert len(tables.subacute) > 50
    assert len(tables.mh_admitted) > 30
    assert len(tables.mh_community) > 30
    assert len(tables.non_admitted) > 100
    assert len(tables.aecc) > 100
    assert len(tables.udg) >= 17


def test_acute_inlier_band(tables):
    # 801A: ALOS 25.1, inlier 7-72, inlier weight 9.2472
    r = acute.episode_nwau(tables, "801A", los=20)
    assert r["payment_class"] == "inlier"
    assert r["base_nwau"] == pytest.approx(9.2472, abs=1e-4)


def test_acute_short_stay_outlier(tables):
    # 801A: SSO base 0.9527, SSO per diem 1.1849, lower bound 7
    r = acute.episode_nwau(tables, "801A", los=3)
    assert r["payment_class"] == "sso"
    expected = 0.9527 + 3 * 1.1849
    assert r["base_nwau"] == pytest.approx(expected, abs=1e-4)


def test_acute_long_stay_outlier(tables):
    # 801A: LSO per diem 0.26, upper bound 72
    r = acute.episode_nwau(tables, "801A", los=80)
    assert r["payment_class"] == "lso"
    expected = 9.2472 + (80 - 72) * 0.26
    assert r["base_nwau"] == pytest.approx(expected, abs=1e-4)


def test_acute_paediatric_multiplier_applies(tables):
    inlier = acute.episode_nwau(tables, "801A", los=20)["base_nwau"]
    paed = acute.episode_nwau(
        tables, "801A", los=20, demographics=Demographics(is_paediatric=True)
    )["base_nwau"]
    # 801A paediatric adjustment is 1.35
    assert paed == pytest.approx(inlier * 1.35, rel=1e-4)


def test_subacute_inlier(tables):
    # 5AZ1: inlier weight 13.4327, ALOS 50.8, bounds 32-70
    r = subacute.episode_nwau(tables, "5AZ1", los=50)
    assert r["payment_class"] == "inlier"
    assert r["base_nwau"] == pytest.approx(13.4327, abs=1e-4)


def test_subacute_average_daily_rate(tables):
    rates = subacute.average_daily_rate_by_care_type(tables, NEP)
    assert set(rates).issuperset({"Rehabilitation", "Maintenance", "Palliative Care"})
    for stats in rates.values():
        assert stats["average_daily_rate_aud"] > 0
        assert stats["min_aud"] <= stats["average_daily_rate_aud"] <= stats["max_aud"]


def test_mh_admitted_sso(tables):
    # 101Z: SSO base 0.427, per diem 1.3204, inlier 1.7474, LB 1, UB 4
    r = mh_admitted.phase_nwau(tables, "101Z", los=2)
    assert r["payment_class"] == "inlier"
    assert r["base_nwau"] == pytest.approx(1.7474, abs=1e-4)


def test_mh_community_with_consumer(tables):
    r = mh_community.contact_nwau(tables, "201Z", contact_with_consumer=True)
    # 201Z: with-consumer 0.0872
    assert r["base_nwau"] == pytest.approx(0.0872, abs=1e-4)
    r2 = mh_community.contact_nwau(tables, "201Z", contact_with_consumer=False)
    assert r2["base_nwau"] == pytest.approx(0.0575, abs=1e-4)


def test_aecc_lookup(tables):
    r = aecc.presentation_nwau(tables, "E0001Z")
    assert r["base_nwau"] == pytest.approx(0.0355, abs=1e-4)


def test_udg_lookup(tables):
    r = udg.presentation_nwau(tables, "UDG01")
    assert r["base_nwau"] == pytest.approx(0.379, abs=1e-4)


def test_unknown_code_raises(tables):
    with pytest.raises(KeyError):
        acute.episode_nwau(tables, "ZZZZ", los=5)
