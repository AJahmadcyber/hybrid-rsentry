#!/usr/bin/env python3
"""
test_pdf_report.py — Seed diverse synthetic events + verify /with-events
returns rich data ready for the new PDF generator.

Usage:
    python3 test_pdf_report.py            # seed + verify
    python3 test_pdf_report.py --no-seed  # verify only
"""
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

BASE = "http://localhost:8000"
HOST = "kali"

NOW = datetime.now(timezone.utc)
def ago(minutes=0, hours=0):
    return (NOW - timedelta(minutes=minutes, hours=hours)).isoformat()

# Diverse fixtures — every event type, every severity, every detail shape
EVENTS = [
    {   # 1. Classic ransomware move-and-encrypt on canary  → CRITICAL
        "host_id": HOST, "timestamp": ago(minutes=1),
        "event_type": "CANARY_TOUCHED", "severity": "CRITICAL",
        "pid": 4521, "process_name": "ransomware.py",
        "file_path": "/home/kali/Documents/canary_invoice_Q1.pdf",
        "lineage_score": 87.5, "entropy_delta": 0.0, "canary_hit": True,
        "details": {
            "sub_type": "moved",
            "dest": "/tmp/.locked/invoice.encrypted",
            "combined_score": 94.2,
            "sha256": "a3f5b8c2d1e7f9a4b6c8d2e5f7a9b3c1d4e6f8a2b5c7d9e1f3a5b8c2d4e6f8a0",
        },
    },
    {   # 2. Entropy spike with full lineage chain → CRITICAL
        "host_id": HOST, "timestamp": ago(minutes=2),
        "event_type": "ENTROPY_SPIKE", "severity": "CRITICAL",
        "pid": 4521, "process_name": "ransomware.py",
        "file_path": "/home/kali/Documents/budget_2026.xlsx",
        "lineage_score": 78.3, "entropy_delta": 7.42, "canary_hit": False,
        "details": {
            "original_event": "modified",
            "combined_score": 89.6,
            "lineage_reasons": ["unusual_child_of_bash", "rapid_file_writes", "high_entropy_output"],
            "ancestors": ["/bin/bash[3201]", "/usr/bin/python3[4521]", "ransomware.py[4521]"],
            "sha256": "b4f6c8a1d3e5f7b9c2d4e6f8a1b3c5d7e9f1a3b5c7d9e2f4a6b8c1d3e5f7a9b2",
        },
    },
    {   # 3. Suspicious process anomaly → HIGH
        "host_id": HOST, "timestamp": ago(minutes=3),
        "event_type": "PROCESS_ANOMALY", "severity": "HIGH",
        "pid": 4521, "process_name": "python3", "file_path": "",
        "lineage_score": 65.0, "entropy_delta": 0.0, "canary_hit": False,
        "details": {
            "combined_score": 72.4,
            "lineage_reasons": ["unexpected_descendant", "no_tty"],
            "ancestors": ["/bin/sh[3198]", "/bin/bash[3201]"],
        },
    },
    {   # 4. Combined alert (highest scoring) → CRITICAL
        "host_id": HOST, "timestamp": ago(minutes=4),
        "event_type": "COMBINED_ALERT", "severity": "CRITICAL",
        "pid": 4521, "process_name": "encryptor.elf",
        "file_path": "/home/kali/Documents/photos",
        "lineage_score": 92.1, "entropy_delta": 6.88, "canary_hit": True,
        "details": {
            "combined_score": 96.7,
            "lineage_reasons": ["high_entropy", "canary_match", "suspicious_parent"],
            "ancestors": ["/bin/bash[3201]", "/tmp/staging[4500]", "encryptor.elf[4521]"],
            "sha256": "c5e7d9a2b4f6c8a1d3e5f7b9c2d4e6f8a1b3c5d7e9f1a3b5c7d9e2f4a6b8c1d3",
        },
    },
    {   # 5. Benign-ish canary read → MEDIUM
        "host_id": HOST, "timestamp": ago(minutes=10),
        "event_type": "CANARY_TOUCHED", "severity": "MEDIUM",
        "pid": 2105, "process_name": "find",
        "file_path": "/home/kali/Documents/canary_taxes.docx",
        "lineage_score": 12.5, "entropy_delta": 0.0, "canary_hit": True,
        "details": {"sub_type": "read", "combined_score": 28.4},
    },
    {   # 6. Legitimate compression entropy spike → HIGH
        "host_id": HOST, "timestamp": ago(minutes=15),
        "event_type": "ENTROPY_SPIKE", "severity": "HIGH",
        "pid": 3891, "process_name": "tar",
        "file_path": "/home/kali/backups/archive_2026_05.tar.gz",
        "lineage_score": 35.0, "entropy_delta": 5.21, "canary_hit": False,
        "details": {
            "original_event": "created",
            "combined_score": 58.3,
            "lineage_reasons": ["legitimate_compression"],
            "ancestors": ["/usr/bin/tar[3891]"],
        },
    },
    {   # 7. Containment confirmation → HIGH
        "host_id": HOST, "timestamp": ago(minutes=2, hours=0),
        "event_type": "CONTAINMENT_TRIGGERED", "severity": "HIGH",
        "pid": 4521, "process_name": "ransomware.py", "file_path": "",
        "lineage_score": 92.1, "entropy_delta": 0.0, "canary_hit": False,
        "details": {
            "action": "SIGSTOP",
            "combined_score": 96.7,
            "frozen_pids": [4521, 4500, 3201],
        },
    },
    {   # 8. Low-noise process anomaly → LOW
        "host_id": HOST, "timestamp": ago(hours=1),
        "event_type": "PROCESS_ANOMALY", "severity": "LOW",
        "pid": 1024, "process_name": "cron", "file_path": "",
        "lineage_score": 8.0, "entropy_delta": 0.0, "canary_hit": False,
        "details": {"combined_score": 15.2, "lineage_reasons": ["scheduled_job"]},
    },
]


def seed():
    print(f"🌱 Seeding {len(EVENTS)} synthetic events into {BASE} …")
    created = failed = 0
    for ev in EVENTS:
        try:
            r = requests.post(f"{BASE}/api/events", json=ev, timeout=5)
            if r.status_code in (200, 201):
                created += 1
                print(f"  ✅ {ev['severity']:8s} {ev['event_type']:24s} {ev['process_name']:18s} {ev['file_path'][:55]}")
            else:
                failed += 1
                print(f"  ❌ {r.status_code} :: {r.text[:160]}")
        except Exception as e:
            failed += 1
            print(f"  ❌ exception :: {e}")
    print(f"\n  → Created: {created}/{len(EVENTS)}   Failed: {failed}")
    return created


def verify():
    print("\n🔍 Verifying /api/alerts/with-events …")
    try:
        r = requests.get(f"{BASE}/api/alerts/with-events?limit=500", timeout=5)
    except Exception as e:
        print(f"  ❌ request failed: {e}"); return False
    if not r.ok:
        print(f"  ❌ HTTP {r.status_code}\n{r.text[:300]}"); return False

    data = r.json()
    print(f"  📊 Got {len(data)} alerts back")
    if not data:
        print("  ⚠️  Empty — backend may not auto-create alerts from events. "
              "Check backend/routers/events.py for alert creation logic.")
        return False

    checks = {
        "every alert has nested event": all(a.get("event") for a in data),
        "event has process_name field": all("process_name" in (a.get("event") or {}) for a in data),
        "event has entropy_delta field": all("entropy_delta" in (a.get("event") or {}) for a in data),
        "event has details dict": all(isinstance((a.get("event") or {}).get("details"), dict) for a in data if a.get("event")),
        "at least one CRITICAL": any(a["severity"] == "CRITICAL" for a in data),
        "at least one canary_hit=True": any((a.get("event") or {}).get("canary_hit") for a in data),
        "at least one combined_score": any(((a.get("event") or {}).get("details") or {}).get("combined_score") is not None for a in data),
        "at least one with ancestors": any(((a.get("event") or {}).get("details") or {}).get("ancestors") for a in data),
        "at least one with sha256": any(((a.get("event") or {}).get("details") or {}).get("sha256") for a in data),
    }
    all_ok = True
    for label, ok in checks.items():
        print(f"  {'✅' if ok else '⚠️ '} {label}")
        all_ok = all_ok and ok

    # Show one rich sample
    rich = sorted(
        (a for a in data if ((a.get("event") or {}).get("details") or {}).get("combined_score")),
        key=lambda a: a["event"]["details"]["combined_score"], reverse=True,
    )
    if rich:
        print("\n📄 Top-scoring alert (sample drill-down content):")
        s = rich[0]
        print(json.dumps(s, indent=2, default=str)[:900])
    return all_ok


def preview():
    print("\n📋 PDF distribution preview")
    r = requests.get(f"{BASE}/api/alerts/with-events?limit=500", timeout=5)
    if not r.ok: return
    data = r.json()
    by_sev, by_type, by_proc = {}, {}, {}
    for a in data:
        by_sev[a["severity"]] = by_sev.get(a["severity"], 0) + 1
        ev = a.get("event") or {}
        by_type[ev.get("event_type", "?")] = by_type.get(ev.get("event_type", "?"), 0) + 1
        by_proc[ev.get("process_name", "?")] = by_proc.get(ev.get("process_name", "?"), 0) + 1
    print("  Severity distribution:")
    for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        print(f"    {s:10s} {by_sev.get(s, 0)}")
    print("  Event types:")
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {t:25s} {n}")
    print("  Top processes:")
    for p, n in sorted(by_proc.items(), key=lambda x: -x[1])[:6]:
        print(f"    {p:25s} {n}")
    crit_high = sum(1 for a in data if a["severity"] in ("CRITICAL", "HIGH"))
    print(f"\n  📄 Drill-down section: {crit_high} cards")
    print(f"  📄 Main log table:    {len(data)} rows")


if __name__ == "__main__":
    if "--no-seed" not in sys.argv:
        seed()
    ok = verify()
    preview()
    print()
    if ok:
        print("✅ Ready. Open dashboard → Reports → Export PDF.")
        sys.exit(0)
    else:
        print("⚠️  Some checks failed — fix backend first or check events router.")
        sys.exit(1)
