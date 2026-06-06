# Containment PID Resolution Fix

**Date:** 2026-06-01
**File changed:** `agent/monitor.py`
**Status:** Applied locally (not yet committed/pushed at time of writing)

---

## Symptom

The auto-containment notification tied to "SIGSTOP the PID" was always generic —
it reported an **unknown / pid=0 process** instead of the real offending process,
and no process was ever actually frozen or killed.

## Root cause

`watchdog` / `inotify` **does not report which process touched a file.** Every
canary event therefore arrived at the agent with `pid=0, process_name="unknown"`:

| Handler | Old behaviour |
|---|---|
| `on_modified` (canary) | `_handle_event(pid=0)` → containment hit the `pid==0` else-branch → sent a **generic** `CONTAINMENT_TRIGGERED` alert. Nothing frozen/killed. |
| `on_deleted` (canary) | Sent a `CANARY_TOUCHED` event with `pid=0` and **never called containment at all.** |
| `on_moved` (canary) | Same as delete — event only, no containment. |

The `agent/containment.py` pipeline (SIGSTOP → /proc evidence → iptables DROP →
SIGKILL) was correct; it was simply **never invoked with a real PID**.

## Fix

All changes are in `agent/monitor.py`.

### 1. `_resolve_offending_pid(path)` — reconstruct the PID from `/proc`

The agent runs as root (`sudo -E`), so it can inspect every process:

1. **Definitive:** a process currently holding the **exact file open** → returned
   immediately as the offender.
2. **Fallback heuristic:** the process with the most files open inside the
   canary's directory / `WATCH_PATH` (ransomware encrypts in bulk); ties broken
   toward the most recently spawned process.

A `NEVER_AUTO_KILL` set protects critical processes (display server, GUI shell,
file managers, browsers, the agent/backend itself, Docker) from ever being
selected for the kill path.

### 2. Real containment wired into all three canary paths

- `_handle_event` now resolves the PID for a canary hit before emitting the event,
  so the event **and** containment target the correct PID.
- `on_deleted` and `on_moved` now route through a new
  `_canary_alert_and_contain()` helper that emits the event **and** fires real
  `_trigger_containment()` (full SIGSTOP → SIGKILL pipeline).
- If no PID can be resolved (e.g. a one-shot `rm` that already exited), it falls
  back to the alert-only path — which is the correct, safe behaviour.

### 3. Markov self-trigger guard (related latent bug)

`is_canary()` matches purely on the `AAA_*.txt` name, so the Markov repositioner's
own `shutil.move` of canary files looked like an attacker hit — and after fix #2
would have attempted containment on the agent's own housekeeping.

The reposition loop now calls `handler.suppress_path()` on the old and new canary
paths; the handlers ignore suppressed paths for ~15 seconds.

## New / changed symbols in `agent/monitor.py`

| Symbol | Purpose |
|---|---|
| `NEVER_AUTO_KILL` (module set) | Processes that must never be auto-killed |
| `RsentryEventHandler._resolve_offending_pid(path)` | `/proc`-based PID resolver |
| `RsentryEventHandler._canary_alert_and_contain(path, sub_type, dest)` | Emit event + real containment for delete/move canary hits |
| `RsentryEventHandler.suppress_path(path, ttl=15.0)` | Mask agent's own Markov moves |
| `RsentryEventHandler._is_suppressed(path)` | Check suppression window |
| `from typing import Optional` | Added import |

## How to test on Kali

Restart the agent (Terminal 4):

```bash
cd ~/hybrid-rsentry && set -a && source .env && set +a && \
  sudo -E ~/hybrid-rsentry/venv/bin/python -m agent.monitor
```

Trigger a canary hit where a live process is the offender:

```bash
f=$(find /home/mohammad/Documents -name 'AAA_*.txt' | head -1); echo x >> "$f"
```

Expected agent log:

```
Resolved offending PID <N> (<name>) — holds <path> open
SIGSTOP sent to PID <N>
... evidence captured ...
SIGKILL sent to PID <N>
=== CONTAINMENT COMPLETE PID <N> ... ===
```

The dashboard `CONTAINMENT_TRIGGERED` notification now shows the **real PID and
process name** instead of the generic "unknown".

### Note on detection timing

The strongest signal is a process **holding the canary open** when inotify fires.
A `rm`/`mv` from a shell closes the descriptor and exits before the event is
delivered, so those rely on the fallback heuristic (a process still holding other
files open in the watch dir) — which is exactly the real-ransomware scenario. A
one-shot command that exits instantly resolves to `pid=0` and the alert-only path,
which is correct.
