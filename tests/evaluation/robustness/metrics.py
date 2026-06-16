#!/usr/bin/env python3
"""
tests/evaluation/robustness/metrics.py — Robustness axis metrics. [NO ROOT]

Pure functions over robustness trial records (each carries a ``condition`` —
baseline or ablate_<layer> — plus ``family_or_class``, ``detected``,
``layer_fired``, and ``base_sample_id`` for pairing). Implements design §3:

  * ablation_table       — detection rate + Wilson CI per (condition × family)
  * layer_contribution   — primary layer (modal at baseline) vs backup-when-off;
                           flags each (family, primary) as necessary or redundant
  * mcnemar_paired       — McNemar's EXACT test on paired per-sample detection
                           (same samples, layer on vs off) — paired binary, NOT a
                           two-sample test. Exact binomial on discordant pairs via
                           scipy.stats.binomtest (not hand-rolled).
  * holm_bonferroni      — step-down family-wise error control across contrasts
  * rate_drop            — detection-rate drop (effect size) + the two Wilson CIs

Statistical choices (§3.5): McNemar because the outcomes are PAIRED binary (the
SAME malicious samples, with a layer enabled vs disabled); Holm–Bonferroni to
control the family-wise error rate across the multiple ablation contrasts.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Sequence, Tuple, Union

from scipy.stats import binomtest

from tests.evaluation.efficacy.metrics import (  # reuse — do not reinvent
    WARMUP_PREFIX, _plan_trials, wilson_ci,
)

BEHAVIORAL_LAYERS = ("rename", "write_offset", "entropy", "canary")
CONDITIONS = ("baseline", "ablate_rename", "ablate_write_offset",
              "ablate_entropy", "ablate_canary")
NAN = float("nan")


def _base_id(t: dict) -> str:
    return t.get("base_sample_id") or t.get("sample_id", "")


# --------------------------------------------------------------------------- #
# Ablation matrix
# --------------------------------------------------------------------------- #

def ablation_table(trials: List[dict]) -> Dict[str, Dict[str, dict]]:
    """{condition: {family: {n, detected, rate, ci:(lo,hi)}}} (warm-up excluded)."""
    groups: Dict[str, Dict[str, List[dict]]] = {}
    for t in _plan_trials(trials):
        cond = t.get("condition", "baseline")
        fam = t.get("family_or_class", "?")
        groups.setdefault(cond, {}).setdefault(fam, []).append(t)
    table: Dict[str, Dict[str, dict]] = {}
    for cond, fams in groups.items():
        table[cond] = {}
        for fam, ts in fams.items():
            n = len(ts)
            det = sum(1 for x in ts if x.get("detected"))
            table[cond][fam] = {"n": n, "detected": det,
                                "rate": (det / n if n else NAN),
                                "ci": list(wilson_ci(det, n))}
    return table


def _detected_by_base(trials: List[dict], condition: str, family: str) -> Dict[str, bool]:
    """{base_sample_id: detected} for one condition+family (for paired tests)."""
    out: Dict[str, bool] = {}
    for t in _plan_trials(trials):
        if t.get("condition") == condition and t.get("family_or_class") == family:
            out[_base_id(t)] = bool(t.get("detected"))
    return out


# --------------------------------------------------------------------------- #
# McNemar (paired) + Holm–Bonferroni
# --------------------------------------------------------------------------- #

def mcnemar_paired(baseline: Union[Dict[str, bool], Sequence[bool]],
                   ablated: Union[Dict[str, bool], Sequence[bool]]) -> Tuple[float, float]:
    """Exact McNemar's test on paired binary detection outcomes.

    Accepts dicts {base_id: detected} (paired by key) or aligned bool sequences.
    Discordant pairs: b = detected at baseline but NOT when ablated (lost);
    c = not at baseline but detected when ablated (gained). Returns
    (chi2_continuity_corrected, p_exact). p is the EXACT two-sided binomial test
    on the discordant pairs (scipy.stats.binomtest, p=0.5). No discordance →
    (0.0, 1.0)."""
    if isinstance(baseline, dict) and isinstance(ablated, dict):
        keys = sorted(set(baseline) & set(ablated))
        b_seq = [baseline[k] for k in keys]
        a_seq = [ablated[k] for k in keys]
    else:
        b_seq, a_seq = list(baseline), list(ablated)
    b = sum(1 for x, y in zip(b_seq, a_seq) if x and not y)
    c = sum(1 for x, y in zip(b_seq, a_seq) if (not x) and y)
    nd = b + c
    if nd == 0:
        return (0.0, 1.0)
    chi2_cc = (abs(b - c) - 1) ** 2 / nd
    p = float(binomtest(min(b, c), nd, 0.5, alternative="two-sided").pvalue)
    return (chi2_cc, p)


def holm_bonferroni(pvalues: Union[Dict[str, float], Sequence[float]],
                    alpha: float = 0.05):
    """Step-down Holm–Bonferroni adjusted p-values. Sort ascending; the i-th
    smallest (0-based rank) is multiplied by (m - rank) and made monotone
    non-decreasing, capped at 1. Returns a dict{label: adj_p} for dict input, or
    a list aligned to the input for sequence input. (alpha is accepted for API
    symmetry; adjusted p's are compared to alpha by the caller.)"""
    items = (list(pvalues.items()) if isinstance(pvalues, dict)
             else list(enumerate(pvalues)))
    m = len(items)
    if m == 0:
        return {} if isinstance(pvalues, dict) else []
    order = sorted(range(m), key=lambda i: items[i][1])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * items[idx][1]))
        adj[idx] = running
    if isinstance(pvalues, dict):
        return {items[i][0]: adj[i] for i in range(m)}
    return adj


# --------------------------------------------------------------------------- #
# Effect size + layer contribution
# --------------------------------------------------------------------------- #

def rate_drop(trials: List[dict], family: str, condition: str) -> Union[dict, None]:
    """Detection-rate drop (effect size) for one family under one ablation, with
    the two Wilson CIs. {baseline_rate, ablated_rate, drop, baseline_ci, ablated_ci}."""
    tbl = ablation_table(trials)
    b = tbl.get("baseline", {}).get(family)
    a = tbl.get(condition, {}).get(family)
    if not b or not a:
        return None
    return {"baseline_rate": b["rate"], "ablated_rate": a["rate"],
            "drop": (b["rate"] - a["rate"]
                     if not (math.isnan(b["rate"]) or math.isnan(a["rate"])) else NAN),
            "baseline_ci": b["ci"], "ablated_ci": a["ci"]}


def layer_contribution(trials: List[dict]) -> Dict[str, dict]:
    """Per family: the PRIMARY layer (modal layer_fired at baseline), what fires
    when that primary is ablated (backup distribution + rate), and whether the
    layer is NECESSARY (family drops to ~undetected when it's off) or REDUNDANT
    (still caught by a backup → defence-in-depth)."""
    plan = _plan_trials(trials)
    families = sorted({t.get("family_or_class") for t in plan
                       if t.get("condition") == "baseline"})
    out: Dict[str, dict] = {}
    for fam in families:
        base = [t for t in plan if t.get("condition") == "baseline"
                and t.get("family_or_class") == fam]
        layers = Counter(t.get("layer_fired") for t in base
                         if t.get("detected") and t.get("layer_fired"))
        primary = layers.most_common(1)[0][0] if layers else None
        cond = f"ablate_{primary}" if primary in BEHAVIORAL_LAYERS else None

        rate_off = None
        backup = Counter()
        if cond:
            ab = [t for t in plan if t.get("condition") == cond
                  and t.get("family_or_class") == fam]
            if ab:
                rate_off = sum(1 for t in ab if t.get("detected")) / len(ab)
                backup = Counter(t.get("layer_fired") for t in ab
                                 if t.get("detected") and t.get("layer_fired"))
        out[fam] = {
            "primary": primary,
            "primary_layers": dict(layers),
            "ablate_primary_condition": cond,
            "rate_when_primary_off": rate_off,
            "backup_layers": dict(backup),
            # necessary: removing the primary collapses detection (no backup).
            "necessary": (rate_off is not None and rate_off <= 0.01),
            # redundant: still caught when the primary is off (a backup covers it).
            "redundant": (rate_off is not None and rate_off >= 0.99),
        }
    return out
