# Changelog

All notable changes to Hybrid R-Sentry are documented here.

---

## [Unreleased]

### Open
- Frontend CRA → Vite migration (removes 26 build-toolchain npm alerts)
- Integration tests (tests/integration/ is currently empty)
- Major dependency bumps pending test: React 18→19, watchdog 4→6, websockets 12→16, date-fns 3→4, uvicorn 0.30→0.48, lucide-react 0.395→1.16

---

## [1.4.0] — 2026-05-29

### Added
- **Landing page deployed** — cinematic 3D landing page live at https://mohhudib.github.io/hybrid-rsentry/
  (React Three Fiber + Framer Motion, all 8 sections, lazy-loaded 3D canvases)
- **Unit test suite** — 71 tests, 89% coverage on `entropy.py`, `lineage.py`, `adaptive.py`, severity logic, and simulation safety (`tests/unit/`)
- **Host-aware PDF export** — `ReportsPage.jsx`: Hosts Overview table on page 1 showing per-host alert breakdown; shortened host UUIDs in Alerts Log; auto-dump of unknown `details` keys in drill-down cards
- **requirements-dev.txt** — pinned dev dependencies for reproducible test environment
- **pytest.ini** — `unit` and `integration` markers configured

### Fixed
- **Canary git corruption prevention** — three-layer fix: `AAA_*.txt` excluded in `.gitignore`; `_validate_watch_path()` in `monitor.py` exits if `WATCH_PATH` is inside a git repo; `_is_safe_target()` in `adaptive.py` blocks Markov repositioner from targeting `.git/`, `/proc/`, `/sys/`, `/dev/`, `/run/`
- Removed accidentally committed canary files `AAA_008.txt` and `simulations/AAA_014.txt`

### Dependencies
- `structlog` bumped 24.2.0 → 25.5.0
- `networkx` bumped 3.3 → 3.6.1

---

## [1.3.0] — 2026-05-26

### Added
- **AI WebSocket fix** — `App.jsx` now handles both `ai_analysis` and `ai_analysis_update` message types; previously AJahmadcyber's tasks.py change broke the AI Analyst page
- **test_event.sh** — one-command pipeline test: sends a `CANARY_TOUCHED` event and verifies the full alert + AI analysis flow
- **start.sh** — one-command startup script that launches all 5 processes and logs to `/tmp/rsentry-*.log`

### Fixed
- docker-compose.yml: Celery container now receives `NVIDIA_API_KEY` and `NVIDIA_API_KEY_ALERTS`
- `entropy.py`: memory cap (5 000 files, LRU evict) + partial reads (65 KB) prevents OOM on large WATCH_PATHs
- `exceptions.py`: smart temp-dir filter — files in `/tmp/` with document extensions bypass the whitelist

---

## [1.2.0] — 2026-05-25

### Added
- **Multi-provider AI fallback chain** — Cerebras (optional, fastest) → NVIDIA/Groq key 1 → NVIDIA/Groq key 2; Groq keys auto-detected by `gsk_` prefix; backward compatible with old `NVIDIA_API_KEY` / `NVIDIA_API_KEY_ALERTS` names
- **Tree-aware containment** — `containment.py` now stops and kills the entire process tree (two-sweep enumeration); collects evidence across up to 48 files per tree
- **dpkg hash verification** — `lineage.py` verifies process binary against 416 K dpkg SHA-256 hashes (MATCH / MISMATCH / UNKNOWN verdicts); SHA-256 cache (512-entry LRU); rapid process exit detection (40-point baseline score)
- **Ransomware extension detection** — `monitor.py`: renames to `.enc`, `.locked`, `.wcry`, `.crypted` etc. fire CRITICAL (if source was a document) or HIGH; canary deletion fires CRITICAL; new files with ransomware extensions fire HIGH
- **PDF forensic export** — `ReportsPage.jsx`: landscape A4, date filter, severity filter, per-alert drill-down cards, AI analysis included; SHA-256 integrity footer on every page
- **Forensic export endpoint** — `GET /api/alerts/{id}/forensic-export`
- **PENDING state** — Celery publishes a PENDING WebSocket message immediately, then updates with the real AI result
- **AI results Redis cache** — 24-hour cache for forensic export
- **Auto-containment for extension renames** — `events.py`: `RANSOMWARE_RENAME` and `RANSOMWARE_CREATED` events trigger containment explicitly

### Fixed
- `ai_analyst.py`: `_get_client_cerebras()` returns `None` instead of raising `RuntimeError` when `AI_API_KEY_CEREBRAS` is not set; `_call_with_fallback()` skips `None` clients silently
- `events.py`: canary-moved events now correctly create alerts (previously silently missed)
- `lineage.py`: score improvements, SHA-256 cache, early exit on rapid process exit, `pid=0` handling

---

## [1.1.0] — 2026-05-22

### Fixed
- `alerts.py`: `analyze_alert` endpoint now passes correct `alert_id` (not `event_id`) to `analyze_alert_ai` task — auto-acknowledge now works end-to-end
- `alerts.py`: embeds `event_id` in `event_data` so the AI Analyst page can display on-demand analysis cards
- `tasks.py`: `analyze_alert_ai` publishes `event_id` in the Redis message so `App.jsx` can match and render the correct card
- `hosts.py`: `/api/hosts/{id}/risk` now returns `alert_count` and `event_count` — HostsPage risk panel no longer shows `—`
- `client.py`: `send_containment_complete` no longer uses wrong dict key `"name"` from `ContainmentResult`
- `CLAUDE.md` + `setup.sh`: startup for Terminal 2 (uvicorn) and Terminal 3 (Celery) now includes `set -a && source .env && set +a`

---

## [1.0.1] — 2026-05-12

### Security
- Removed `python-jose` from `requirements.txt` (CVE-2024-33664, CVE-2024-33663 — algorithm confusion attacks; was never imported)
- `docker-compose.yml`: replaced hardcoded Postgres password with `${POSTGRES_PASSWORD:-rsentry_pass}`
- `database.py`: raises `RuntimeError` if `DATABASE_URL` is not set (removed hardcoded fallback `postgresql://rsentry:rsentry_pass@localhost/rsentry_db`)

---

## [1.0.0] — 2026-04-27

### Added
- **Detection Engine** — Shannon entropy analysis, process lineage scoring, canary file monitoring
- **Markov Chain Repositioner** — adaptive canary placement based on filesystem access patterns
- **Auto-Containment Pipeline** — SIGSTOP → evidence capture → iptables DROP → SIGKILL
- **AI Threat Analyst** — LLM-powered event and alert classification with dual API key rotation
- **System Health Check** — AI analysis of recent activity patterns
- **Auto-ACK** — automatically acknowledges alerts classified as Benign or LOW risk
- **Live Dashboard** — React 18 with real-time WebSocket feed (3 Redis pub/sub channels)
- **Alert Management** — per-alert ACK, bulk acknowledge, live count badges
- **Host Risk Gauge** — radial score that recalculates after every acknowledgement
- **False Positive Suppression** — whitelist system for browsers, package managers, system paths, archives
- **Celery Workers** — AI analysis, WebSocket push, host risk scoring, auto-ACK tasks
- **REST API** — events, alerts (`/counts` endpoint), hosts, containment endpoints
- **Docker Compose** — PostgreSQL + Redis infrastructure
- **Dependabot** — weekly dependency scanning for pip, npm, and Docker
