"""Pooling-logic tests — the transitive shared-WC + plant-guard rules.

Programs pool iff they are in the SAME PLANT and share a work center. WCs are globally unique
across the site, so a shared WC already implies the same physical resource; the plant check is a
belt-and-suspenders guard so a mis-entered WC number can never pool across plants.
"""
import os
os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")

from app.engines import rtg_wrapper as W


def test_seed_pooling_matches_original_rule():
    """ELEV+AEGIS pool (Plant 2, share paint WC221); RAD is separate (Plant 3)."""
    groups = W.pool_groups(["ELEV", "RAD", "AEGIS"])
    as_sets = sorted([sorted(g) for g in groups])
    assert ["AEGIS", "ELEV"] in as_sets
    assert ["RAD"] in as_sets


def test_shared_wcs_are_derived():
    """The shared-WC set is derived from routings, not hardcoded; must include paint WC221."""
    shared = W.shared_wcs()
    assert "221" in shared          # paint booth, ELEV+AEGIS
    # a program-specific WC must NOT be shared
    assert "AEROA" not in shared    # radome assembly, RAD only


def test_plant_guard_blocks_cross_plant_pool(monkeypatch):
    """Even if two programs in different plants shared a WC number, they must not pool."""
    monkeypatch.setattr(W, "_program_wcs", lambda c: {"999"} if c in ("ELEV", "RAD") else set())
    monkeypatch.setattr(W, "_plants", lambda codes: {"ELEV": "Plant 2", "RAD": "Plant 3"})
    groups = W.pool_groups(["ELEV", "RAD"])
    assert sorted([sorted(g) for g in groups]) == [["ELEV"], ["RAD"]]


def test_same_plant_shared_wc_pools(monkeypatch):
    monkeypatch.setattr(W, "_program_wcs", lambda c: {"999"} if c in ("ELEV", "RAD") else set())
    monkeypatch.setattr(W, "_plants", lambda codes: {"ELEV": "Plant 2", "RAD": "Plant 2"})
    groups = W.pool_groups(["ELEV", "RAD"])
    assert [sorted(g) for g in groups] == [["ELEV", "RAD"]]
