#!/usr/bin/env python3
"""
tests/evaluation/robustness/test_metrics.py — unit tests for robustness metrics.
[NO ROOT] scipy required (exact McNemar) — skip, not hand-roll, if absent.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("scipy", reason="scipy required for exact McNemar")

from tests.evaluation.robustness import metrics

TOL = 1e-9


def _close(a, b):
    return math.isclose(a, b, abs_tol=TOL)


def _t(cond, fam, idx, detected, layer=None):
    return {"sample_id": f"{cond}__mal_{fam}_{idx:03d}",
            "base_sample_id": f"mal_{fam}_{idx:03d}", "condition": cond,
            "family_or_class": fam, "detected": detected, "layer_fired": layer}


def test_ablation_table_rates_and_warmup_exclusion():
    trials = ([_t("baseline", "akira", i, True, "rename") for i in range(10)] +
              [_t("ablate_rename", "akira", i, i < 9, "write_offset") for i in range(10)] +
              [{"sample_id": "warmup_000", "condition": "warmup",
                "family_or_class": "akira", "detected": True}])   # excluded
    tbl = metrics.ablation_table(trials)
    assert tbl["baseline"]["akira"]["n"] == 10           # warm-up not counted
    assert _close(tbl["baseline"]["akira"]["rate"], 1.0)
    assert _close(tbl["ablate_rename"]["akira"]["rate"], 0.9)   # 9/10 (backup caught 9)


def test_mcnemar_exact_pinned():
    # baseline detects all 10, ablated detects none → b=10 lost, c=0 gained.
    # chi2 (continuity-corrected) = (|10-0|-1)^2 / 10 = 81/10 = 8.1
    # exact two-sided binomial on discordant pairs = 2 * 0.5^10 = 0.001953125
    base = {f"s{i}": True for i in range(10)}
    ablated = {f"s{i}": False for i in range(10)}
    chi2, p = metrics.mcnemar_paired(base, ablated)
    assert _close(chi2, 8.1), chi2
    assert _close(p, 0.001953125), p
    # no discordance → no change
    assert metrics.mcnemar_paired({"a": True}, {"a": True}) == (0.0, 1.0)


def test_holm_bonferroni_ordering():
    # m=3; sorted asc: a(.01), c(.03), b(.04)
    # holm: a=min(1,3*.01)=.03 ; c=max(.03,min(1,2*.03)=.06)=.06 ; b=max(.06,1*.04)=.06
    adj = metrics.holm_bonferroni({"a": 0.01, "b": 0.04, "c": 0.03})
    assert _close(adj["a"], 0.03)
    assert _close(adj["c"], 0.06)
    assert _close(adj["b"], 0.06)             # monotone (can't drop below earlier)
    assert metrics.holm_bonferroni({}) == {}


def test_layer_contribution_necessity_and_redundancy():
    trials = []
    # akira: baseline caught via rename; with rename OFF still caught (write_offset
    # backup) → REDUNDANT (defence-in-depth).
    for i in range(10):
        trials.append(_t("baseline", "akira", i, True, "rename"))
        trials.append(_t("ablate_rename", "akira", i, True, "write_offset"))
    # entropy_only: baseline caught via entropy; with entropy OFF → DROPS → NECESSARY.
    for i in range(10):
        trials.append(_t("baseline", "entropy_only", i, True, "entropy"))
        trials.append(_t("ablate_entropy", "entropy_only", i, False, None))
    # canary_touch: baseline via canary; with canary OFF → DROPS → NECESSARY.
    for i in range(10):
        trials.append(_t("baseline", "canary_touch", i, True, "canary"))
        trials.append(_t("ablate_canary", "canary_touch", i, False, None))

    lc = metrics.layer_contribution(trials)
    assert lc["akira"]["primary"] == "rename"
    assert lc["akira"]["redundant"] is True and lc["akira"]["necessary"] is False
    assert lc["akira"]["backup_layers"] == {"write_offset": 10}

    assert lc["entropy_only"]["primary"] == "entropy"
    assert lc["entropy_only"]["necessary"] is True and lc["entropy_only"]["redundant"] is False
    assert _close(lc["entropy_only"]["rate_when_primary_off"], 0.0)

    assert lc["canary_touch"]["primary"] == "canary"
    assert lc["canary_touch"]["necessary"] is True       # necessity proof #2


def test_rate_drop_effect_size():
    trials = ([_t("baseline", "entropy_only", i, True, "entropy") for i in range(10)] +
              [_t("ablate_entropy", "entropy_only", i, False) for i in range(10)])
    rd = metrics.rate_drop(trials, "entropy_only", "ablate_entropy")
    assert _close(rd["baseline_rate"], 1.0) and _close(rd["ablated_rate"], 0.0)
    assert _close(rd["drop"], 1.0)            # full necessity drop


def test_mcnemar_significant_for_necessity_drop():
    # entropy_only baseline all detected, ablate_entropy all undetected over n=30
    base = {f"s{i}": True for i in range(30)}
    ablated = {f"s{i}": False for i in range(30)}
    _, p = metrics.mcnemar_paired(base, ablated)
    assert p < 0.001                          # a clean necessity drop is highly significant
