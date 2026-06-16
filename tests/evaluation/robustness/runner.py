#!/usr/bin/env python3
"""
tests/evaluation/robustness/runner.py — the ablation sweep. [ROOT]

For each ablation CONDITION (baseline = all layers on; then each single layer
OFF), run the full malicious plan (akira/qilin/lockbit/entropy_only/canary_touch)
and record, per (condition, family), the detection outcome + which layer fired.
The layer toggle is a REAL decision-path ablation (agent ABLATE_<LAYER> env →
build_bpf kernel gate + run_sensor userspace gate); seeding/filesystem state is
identical across conditions, only the gated layer differs.

Reuses harness.run_trial + the integrity guard (warm-up excluded, resumable,
errors recorded, completeness, loud INCOMPLETE banner). Records carry a
``condition`` and ``base_sample_id`` (for McNemar pairing) on top of TrialResult.

Usage (root):
    sudo -E ~/hybrid-rsentry/venv/bin/python -m tests.evaluation.robustness.runner --n 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.evaluation import harness
from tests.evaluation.conftest import RESULTS_DIR, read_trials
from tests.evaluation.corpus import malicious_samples
from tests.evaluation.efficacy.metrics import WARMUP_PREFIX, completeness
from tests.evaluation.robustness import metrics

ROBUSTNESS_RAW = RESULTS_DIR / "robustness_raw.json"
ROBUSTNESS_REPORT = RESULTS_DIR / "robustness_report.json"

# condition → layer_toggles passed to harness.run_trial (None = all layers on).
CONDITION_TOGGLES: Dict[str, Optional[Dict[str, bool]]] = {
    "baseline": None,
    "ablate_rename": {"rename": False},
    "ablate_write_offset": {"write_offset": False},
    "ablate_entropy": {"entropy": False},
    "ablate_canary": {"canary": False},
}


def _append(rec: dict) -> None:
    with open(ROBUSTNESS_RAW, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def _planned(n_per_family: int) -> Dict[str, str]:
    """{robustness_sample_id: condition} for completeness reconciliation."""
    planned: Dict[str, str] = {}
    for cond in CONDITION_TOGGLES:
        for entry in malicious_samples.malicious_plan(n_per_family):
            planned[f"{cond}__{entry['sample_id']}"] = cond
    return planned


def _record(res, cond: str) -> dict:
    d = res.to_dict()
    base_id = d["sample_id"]
    d["base_sample_id"] = base_id
    d["condition"] = cond
    d["sample_id"] = f"{cond}__{base_id}"      # unique across conditions (resumable)
    return d


def write_robustness_report(n_per_family: "int | None" = None) -> dict:
    rows = read_trials(ROBUSTNESS_RAW)
    plan = [r for r in rows if not str(r.get("sample_id", "")).startswith(WARMUP_PREFIX)]
    comp = completeness(plan, _planned(n_per_family)) if n_per_family is not None else None
    report = {
        "_meta": {
            "n_trials": len(plan), "n_per_family": n_per_family,
            "conditions": list(CONDITION_TOGGLES),
            "completeness": comp, "complete": (comp["complete"] if comp else None),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "ablation_table": metrics.ablation_table(plan),
        "layer_contribution": metrics.layer_contribution(plan),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ROBUSTNESS_REPORT.write_text(json.dumps(report, indent=2))
    return report


def run_robustness_sweep(n_per_family: int = 30, *, lsm: bool = True,
                         warmup_k: int = 2, response_timeout: float = 30.0) -> dict:
    if os.geteuid() != 0:
        raise PermissionError("robustness sweep requires root (run_trial starts the agent).")
    completed = {r.get("sample_id") for r in read_trials(ROBUSTNESS_RAW)}
    n_warm = sum(1 for s in completed if str(s).startswith(WARMUP_PREFIX))

    # Warm-up (baseline akira; excluded) — warm dpkg-hash page cache + BPF JIT.
    akira0 = malicious_samples.malicious_plan(1)[0]
    for i in range(warmup_k):
        rid = f"{WARMUP_PREFIX}{i:03d}"
        if rid in completed or n_warm > i:
            print(f"[warmup] skip {rid}")
            continue
        wl = malicious_samples.build_workload(akira0)
        print(f"[warmup] {rid} (EXCLUDED)")
        try:
            res = harness.run_trial(wl, lsm=lsm, enforce=True, response_timeout=response_timeout)
            d = res.to_dict(); d["sample_id"] = rid; d["condition"] = "warmup"
            _append(d)
        except Exception as exc:
            print(f"[warmup] {rid} ERROR (ignored): {type(exc).__name__}: {exc}")

    plan = malicious_samples.malicious_plan(n_per_family)
    total = len(CONDITION_TOGGLES) * len(plan)
    i = 0
    for cond, toggles in CONDITION_TOGGLES.items():
        for entry in plan:
            i += 1
            sid = f"{cond}__{entry['sample_id']}"
            if sid in completed:
                print(f"[robust {i}/{total}] skip {sid}")
                continue
            wl = malicious_samples.build_workload(entry)
            try:
                res = harness.run_trial(wl, lsm=lsm, enforce=True,
                                        layer_toggles=toggles, response_timeout=response_timeout)
                rec = _record(res, cond)
                _append(rec)
                print(f"[robust {i}/{total}] {sid:<34} detected={str(rec['detected']):<5} "
                      f"layer={rec['layer_fired']}")
            except Exception as exc:
                _append({"sample_id": sid, "base_sample_id": entry["sample_id"],
                         "condition": cond, "family_or_class": entry["family"],
                         "detected": False, "layer_fired": None,
                         "error": f"{type(exc).__name__}: {exc}"})
                print(f"[robust {i}/{total}] {sid:<34} ERROR (recorded): "
                      f"{type(exc).__name__}: {exc}")

    write_robustness_report(n_per_family=n_per_family)
    comp = completeness(
        [r for r in read_trials(ROBUSTNESS_RAW)
         if not str(r.get("sample_id", "")).startswith(WARMUP_PREFIX)],
        _planned(n_per_family))
    print(f"\n[robustness] sweep done → {ROBUSTNESS_RAW}")
    print(f"[robustness] COMPLETENESS: ran {comp['ran']}/{comp['planned']}, "
          f"missing={comp['missing']}, errored={comp['errored']}, complete={comp['complete']}")
    if not comp["complete"]:
        print("\n" + "!" * 72)
        print("WARNING: ablation sweep INCOMPLETE — the necessity matrix is partial.")
        for grp, g in sorted(comp["by_group"].items()):
            if g["missing"] or g["errored"]:
                print(f"   {grp:<20} ran {g['ran']}/{g['planned']} "
                      f"missing={len(g['missing'])} errored={len(g['errored'])}")
        print("Re-run (resumable) to fill gaps, then --aggregate-only.")
        print("!" * 72)
    return comp


def main() -> int:
    ap = argparse.ArgumentParser(description="Robustness ablation sweep (root)")
    ap.add_argument("--n", type=int, default=30, dest="n_per_family",
                    help="trials per family per condition (3=smoke, 30=real)")
    ap.add_argument("--warmup", type=int, default=2, dest="warmup_k")
    ap.add_argument("--no-lsm", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--aggregate-only", action="store_true")
    args = ap.parse_args()
    if args.aggregate_only:
        rep = write_robustness_report(n_per_family=args.n_per_family)
        comp = rep["_meta"]["completeness"]
        print(f"[robustness] aggregated → {ROBUSTNESS_REPORT} | "
              f"complete={comp['complete'] if comp else 'n/a'}")
        return 0
    run_robustness_sweep(n_per_family=args.n_per_family, lsm=not args.no_lsm,
                         warmup_k=args.warmup_k, response_timeout=args.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
