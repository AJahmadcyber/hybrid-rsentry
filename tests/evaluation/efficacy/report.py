#!/usr/bin/env python3
"""
tests/evaluation/efficacy/report.py — render the §1 efficacy tables. [NO ROOT]

Reads a trials_raw.json (JSON-lines) — the single source of truth — recomputes
every metric via metrics.py, and prints the four design §1 tables as plain ASCII,
copy-pasteable into the paper:

  [EFFICACY] Confusion Matrix
  [EFFICACY] Core Metrics
  [EFFICACY] Per-Family Detection Rate
  [EFFICACY] Benign Breakdown   (compression / high-entropy row highlighted)

Usage:
    python3 -m tests.evaluation.efficacy.report [path/to/trials_raw.json]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.evaluation.conftest import TRIALS_RAW, read_trials
from tests.evaluation.efficacy import metrics

WARMUP_PREFIX = metrics.WARMUP_PREFIX


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _fmt(x: float) -> str:
    return "n/a" if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:.3f}"


def _ci(lohi) -> str:
    lo, hi = lohi
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (lo, hi)):
        return "n/a"
    return f"[{lo:.3f}, {hi:.3f}]"


def _table(title: str, headers: List[str], rows: List[List[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep = "|" + "|".join("-" * (widths[i] + 2) for i in range(len(headers))) + "|"
    out = [title, line, sep]
    for row in rows:
        out.append("| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #

def confusion_matrix_table(trials: List[dict]) -> str:
    c = metrics.confusion_counts(trials)
    n_mal = c["TP"] + c["FN"]
    n_ben = c["FP"] + c["TN"]
    n_warm = sum(1 for t in trials if str(t.get("sample_id", "")).startswith(WARMUP_PREFIX))
    rows = [
        ["Actual MALICIOUS", f"TP = {c['TP']}", f"FN = {c['FN']}", str(n_mal)],
        ["Actual BENIGN",    f"FP = {c['FP']}", f"TN = {c['TN']}", str(n_ben)],
    ]
    tbl = _table("[EFFICACY] Confusion Matrix  (D = Detection, §0.2/§1.2)",
                 ["", "Predicted: Detected", "Predicted: Not-Detected", "N"], rows)
    return tbl + f"\n(N total = {sum(c.values())}; warmup_excluded = {n_warm})"


def core_metrics_table(trials: List[dict]) -> str:
    c = metrics.confusion_counts(trials)
    f1_ci = metrics.bootstrap_f1_ci(trials)
    specs = [
        ("Recall (TPR)",  "TP/(TP+FN)", metrics.recall(c),      _ci(metrics.metric_ci("recall", c))),
        ("Precision",     "TP/(TP+FP)", metrics.precision(c),   _ci(metrics.metric_ci("precision", c))),
        ("F1",            "2PR/(P+R)",  metrics.f1(c),          _ci(f1_ci) + " (boot)"),
        ("Accuracy",      "(TP+TN)/N",  metrics.accuracy(c),    _ci(metrics.metric_ci("accuracy", c))),
        ("FPR",           "FP/(FP+TN)", metrics.fpr(c),         _ci(metrics.metric_ci("fpr", c))),
        ("FNR",           "FN/(FN+TP)", metrics.fnr(c),         _ci(metrics.metric_ci("fnr", c))),
        ("Specificity",   "TN/(TN+FP)", metrics.specificity(c), _ci(metrics.metric_ci("specificity", c))),
    ]
    rows = [[name, formula, _fmt(val), ci] for name, formula, val, ci in specs]
    return _table("[EFFICACY] Core Metrics  (Wilson 95% CI; F1 = bootstrap 95%)",
                  ["Metric", "Formula", "Value", "95% CI"], rows)


def per_family_table(trials: List[dict]) -> str:
    fam = metrics.per_family_rates(trials)
    rows = []
    for family, d in fam.items():
        layers = ", ".join(f"{k}:{v}" for k, v in sorted(d["layers"].items())) or "-"
        rows.append([family, str(d["n"]), str(d["tp"]), _fmt(d["recall"]),
                     _ci(d["ci"]), d["modal_layer"] or "-", layers])
    if not rows:
        rows = [["(none)", "0", "0", "n/a", "n/a", "-", "-"]]
    return _table("[EFFICACY] Per-Family Detection Rate",
                  ["Family", "N", "Detected", "Rate", "95% CI",
                   "Modal Layer", "Layer Distribution"], rows)


def benign_breakdown_table(trials: List[dict]) -> str:
    ben = metrics.benign_fpr(trials)
    rows = []
    for cls, d in ben.items():
        mark = "  *** HEADLINE (compression/encryption)" if d["headline"] else ""
        rows.append([cls + mark, str(d["n"]), str(d["fp"]), _fmt(d["fpr"]), _ci(d["ci"])])
    if not rows:
        rows = [["(none)", "0", "0", "n/a", "n/a"]]
    return _table("[EFFICACY] Benign Breakdown  (FPR per class; lower is better)",
                  ["Class", "N", "FP", "FPR", "95% CI"], rows)


def render(trials: List[dict]) -> str:
    return "\n\n".join([
        confusion_matrix_table(trials),
        core_metrics_table(trials),
        per_family_table(trials),
        benign_breakdown_table(trials),
    ])


def main() -> int:
    if len(sys.argv) > 1:
        from tests.evaluation.conftest import read_trials as _rt
        trials = _rt(Path(sys.argv[1]))
        src = sys.argv[1]
    else:
        trials = read_trials()
        src = str(TRIALS_RAW)
    if not trials:
        print(f"No trials found at {src}. Run the efficacy sweep first.")
        return 1
    print(f"# Efficacy report — source: {src} ({len(trials)} raw trial records)\n")
    print(render(trials))
    return 0


if __name__ == "__main__":
    sys.exit(main())
