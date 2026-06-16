#!/usr/bin/env python3
"""
sim_canary.py — canary-touch simulation (SAFE). Renames a SEEDED decoy file so
the agent's CANARY layer is the sole detector — the necessity-proof workload for
the Robustness axis (§3) `-canary` ablation.

Behaviour (mirrors tests/integration/test_live_canary.py's locker):
  * Finds decoy files the agent already seeded (prefixes AAA_/aaa_/ZZZ_/zzz_) in
    the target dir and renames one (or a few, bounded) to a LOW-ENTROPY ransom
    extension (e.g. .crab). The low-entropy extension is deliberate: it is NOT
    "encrypted-looking" (Shannon < the rename layer's threshold), so the
    rename/extension layer does NOT treat it as a backup detector — isolating the
    canary layer as the only thing that catches this. So `-canary` makes it DROP.
  * Under enforce+lsm baseline the LSM denies the rename (-EPERM); the locker
    retries (bounded) — each attempt is a canary touch the agent contains
    (layer=canary). Under `-canary` the rename is allowed and not contained.
  * NO encryption, NO writes, NO deletes — only renames of decoys. Bounded by
    --max-files (<=10) and a bounded retry budget (no VM hang).

Emits the --eval-timestamps side-channel (t0 + per-touch) for harness
consistency, exactly like the other sims.

SAFETY: operates only on decoy files (canary prefixes) inside --target; never
touches real corpus. Renames are reversible/irrelevant (decoys are throwaway).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from simulations.sim_common import EvalTimestampWriter, _set_comm

CANARY_PREFIXES = ("AAA_", "aaa_", "ZZZ_", "zzz_")
RANSOM_EXT = ".crab"           # 4 distinct chars → low-entropy ext (rename layer ignores)
RETRY_PER_FILE = 8             # bounded attempts per decoy (LSM denies at baseline)
RETRY_DELAY = 0.15


def _find_decoys(target: str, limit: int) -> list:
    """Decoy files the agent seeded under target (all four canary prefixes)."""
    found = []
    for p in sorted(Path(target).rglob("*")):
        if p.is_file() and p.name.startswith(CANARY_PREFIXES):
            found.append(p)
        if len(found) >= limit:
            break
    return found


def run_canary_attack(target: str, max_files: int = 5, delay: float = 0.1,
                      ts_writer: "EvalTimestampWriter | None" = None) -> dict:
    """Rename up to max_files seeded decoys to a low-entropy ransom ext, retrying
    (bounded) since the LSM denies at baseline. Returns a small stats dict."""
    decoys = _find_decoys(target, max_files)
    stats = {"decoys_found": len(decoys), "rename_attempts": 0,
             "renames_succeeded": 0, "targets": [str(d) for d in decoys]}
    for decoy in decoys:
        locked = Path(str(decoy) + RANSOM_EXT)
        for _ in range(RETRY_PER_FILE):
            if ts_writer is not None:
                ts_writer.touch(str(decoy), "canary_rename")   # first touch == t0
            stats["rename_attempts"] += 1
            try:
                os.rename(decoy, locked)
                stats["renames_succeeded"] += 1
                # If it went through (canary ablated / SIGSTOP-fallback), restore
                # so the next attempt is deterministic and state stays bounded.
                try:
                    os.rename(locked, decoy)
                except OSError:
                    break
            except OSError:
                pass            # -EPERM at baseline (LSM deny) — that's a canary hit
            time.sleep(delay)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Canary-touch simulator (safe)")
    ap.add_argument("--target", required=True,
                    help="dir containing the agent's seeded decoys")
    ap.add_argument("--max-files", type=int, default=5, help="decoys to touch (<=10)")
    ap.add_argument("--delay", type=float, default=0.1)
    ap.add_argument("--no-restore", action="store_true")     # accepted for harness parity
    ap.add_argument("--traversal", default="dfs")            # accepted, unused
    ap.add_argument("--eval-timestamps", default=None, metavar="PATH")
    args, _ = ap.parse_known_args()

    _set_comm("canary-locker")
    max_files = min(args.max_files, 10)        # VM-hang guard
    ts_writer = None
    if args.eval_timestamps:
        ts_writer = EvalTimestampWriter(args.eval_timestamps)
        ts_writer.start(os.getpid())
    try:
        stats = run_canary_attack(args.target, max_files=max_files,
                                  delay=args.delay, ts_writer=ts_writer)
    finally:
        if ts_writer is not None:
            ts_writer.close()
    print(f"[CANARY] decoys={stats['decoys_found']} attempts={stats['rename_attempts']} "
          f"succeeded={stats['renames_succeeded']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
