#!/usr/bin/env python3
"""
tests/evaluation/robustness/report.py — render the §3 robustness tables. [NO ROOT]

Reads robustness_raw.json, recomputes via metrics, prints:
  [ROBUSTNESS] Ablation Matrix     (condition × family → detection rate + CI)
  [ROBUSTNESS] Layer Contribution  (family | primary | backup when primary off | necessary/redundant)
  [ROBUSTNESS] Significance        (contrast | rate drop + CI | McNemar p | Holm-adjusted p)
Completeness banner first.

Usage:
    python3 -m tests.evaluation.robustness.report [path/to/robustness_raw.json]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.evaluation.conftest import read_trials
from tests.evaluation.efficacy.report import _table, _fmt, _ci
from tests.evaluation.robustness import metrics
from tests.evaluation.robustness.runner import ROBUSTNESS_RAW, ROBUSTNESS_REPORT

_ABLATE_CONDITIONS = ("ablate_rename", "ablate_write_offset", "ablate_entropy", "ablate_canary")


def _pval(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _load_completeness() -> "dict | None":
    if not ROBUSTNESS_REPORT.is_file():
        return None
    try:
        return json.loads(ROBUSTNESS_REPORT.read_text()).get("_meta", {}).get("completeness")
    except (OSError, json.JSONDecodeError):
        return None


def completeness_banner(comp: "dict | None") -> str:
    if comp is None:
        return ("[ROBUSTNESS] Completeness: UNKNOWN — no robustness_report.json. Run "
                "the sweep via runner.py so recorded-vs-planned can be reconciled.")
    status = "COMPLETE" if comp["complete"] else "*** INCOMPLETE ***"
    line = (f"[ROBUSTNESS] Completeness: {status}  (ran {comp['ran']}/{comp['planned']} "
            f"planned; missing={comp['missing']}, errored={comp['errored']})")
    if not comp["complete"]:
        line += "\n  The necessity matrix is PARTIAL — drops below are over recorded trials only."
    return line


def ablation_matrix_table(trials: List[dict]) -> str:
    tbl = metrics.ablation_table(trials)
    families = sorted({f for c in tbl.values() for f in c})
    header = ["Condition"] + families
    rows = []
    for cond in metrics.CONDITIONS:
        if cond not in tbl:
            continue
        row = [cond]
        for fam in families:
            cell = tbl[cond].get(fam)
            row.append(f"{_fmt(cell['rate'])} {_ci(cell['ci'])}" if cell else "-")
        rows.append(row)
    return _table("[ROBUSTNESS] Ablation Matrix  (detection rate + Wilson 95% CI per condition × family)",
                  header, rows)


def layer_contribution_table(trials: List[dict]) -> str:
    lc = metrics.layer_contribution(trials)
    rows = []
    n_nec = n_red = n_partial = 0
    for fam, d in sorted(lc.items()):
        if d["necessary"]:
            verdict = "NECESSARY — sole detector (no backup)"; n_nec += 1
        elif d["redundant"]:
            verdict = "REDUNDANT — backup covers (defence-in-depth)"; n_red += 1
        elif d["rate_when_primary_off"] is not None:
            verdict = "PARTIAL — degraded (partial backup)"; n_partial += 1
        else:
            verdict = "n/a"
        backup = ", ".join(f"{k}:{v}" for k, v in sorted(d["backup_layers"].items())) or "none"
        rate_off = (_fmt(d["rate_when_primary_off"])
                    if d["rate_when_primary_off"] is not None else "n/a")
        rows.append([fam, d["primary"] or "-", rate_off, backup, verdict])
    tbl = _table("[ROBUSTNESS] Layer Contribution  (primary = modal layer at baseline; "
                 "rate w/ primary OFF = detection when that layer is ablated)",
                 ["Family", "Primary layer", "Rate w/ primary OFF",
                  "Backup layer(s) when off", "Verdict"], rows)
    # Corpus-level summary — keep the paper claim precise and honest.
    total = n_nec + n_red + n_partial
    if total and n_nec == total:
        summary = (f"\nSummary: ALL {total} layers NECESSARY — each is the UNIQUE catcher "
                   f"for its family. NO backup / defence-in-depth coverage was observed in "
                   f"this corpus: ablating a layer drops its family to undetected, with no "
                   f"other layer compensating. The layers cover ORTHOGONAL behaviours, so "
                   f"the multi-layer design is necessary (not redundant).")
    else:
        summary = (f"\nSummary: necessary={n_nec}, redundant(backup covers)={n_red}, "
                   f"partial={n_partial} (of {total} families). 'Redundant' = another layer "
                   f"provides backup coverage (defence-in-depth); 'necessary' = sole catcher.")
    return tbl + summary


def significance_table(trials: List[dict]) -> str:
    # Build all (family × ablated-condition) contrasts, then Holm-adjust across them.
    tbl = metrics.ablation_table(trials)
    families = sorted(tbl.get("baseline", {}))
    contrasts = []          # (label, family, condition)
    pvals = {}
    for fam in families:
        for cond in _ABLATE_CONDITIONS:
            if cond not in tbl or fam not in tbl[cond]:
                continue
            label = f"{fam} / {cond}"
            base = metrics._detected_by_base(trials, "baseline", fam)
            ab = metrics._detected_by_base(trials, cond, fam)
            _, p = metrics.mcnemar_paired(base, ab)
            contrasts.append((label, fam, cond, p))
            pvals[label] = p
    holm = metrics.holm_bonferroni(pvals) if pvals else {}
    rows = []
    for label, fam, cond, p in contrasts:
        rd = metrics.rate_drop(trials, fam, cond) or {}
        drop = rd.get("drop")
        rows.append([label, _fmt(drop) if drop is not None else "n/a",
                     _ci(rd.get("baseline_ci", (float("nan"),) * 2)),
                     _ci(rd.get("ablated_ci", (float("nan"),) * 2)),
                     _pval(p), _pval(holm.get(label))])
    if not rows:
        rows = [["(none)", "n/a", "n/a", "n/a", "n/a", "n/a"]]
    return _table("[ROBUSTNESS] Significance  (McNemar paired; Holm–Bonferroni family-wise; effect size leads)",
                  ["Contrast (family / ablation)", "rate drop", "baseline CI",
                   "ablated CI", "McNemar p", "Holm p"], rows)


def render(trials: List[dict]) -> str:
    return "\n\n".join([
        completeness_banner(_load_completeness()),
        ablation_matrix_table(trials),
        layer_contribution_table(trials),
        significance_table(trials),
    ])


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROBUSTNESS_RAW
    trials = read_trials(src)
    if not trials:
        print(f"No trials found at {src}. Run the robustness sweep first.")
        return 1
    print(f"# Robustness report — source: {src} ({len(trials)} raw trial records)\n")
    print(render(trials))
    return 0


if __name__ == "__main__":
    sys.exit(main())
