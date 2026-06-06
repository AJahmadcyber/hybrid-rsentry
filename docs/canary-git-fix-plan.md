# Canary Git Corruption — Comprehensive Fix Plan

**For Claude Code to execute on Kali (`~/hybrid-rsentry`)**  
**Created: 2026-05-26**

---

## Background

Canary files (`AAA_*.txt`) created by `agent/adaptive.py` (the Markov repositioner) periodically
appear inside `.git/refs/` — specifically at paths like `.git/refs/heads/AAA_*.txt` or
`.git/refs/remotes/origin/AAA_*.txt`. Git treats any file under `.git/refs/` as a ref, reads
its content as a SHA, and errors with `fatal: bad object refs/remotes/origin/AAA_*.txt` because
the file contains text, not a valid object hash.

**Current workaround (to remove):** `find .git/refs -name "AAA_*" -delete` before every git pull.

**Root causes (two distinct paths):**

1. **Markov repositioner has no path guard.** `adaptive.py:reposition()` calls
   `target_dir.mkdir(parents=True, exist_ok=True)` and `shutil.move()` with whatever directory the
   Markov model predicts as a hotspot. If the model was trained on access events inside the git repo
   (e.g., from an old WATCH_PATH config), `.git/refs/` can score as a high-probability hotspot and
   canaries get moved there directly.

2. **No `.gitignore` coverage for canary filenames.** Even if canaries land in the working tree
   (not in `.git/`), a `git add .` by a contributor accidentally stages them, and `git push` creates
   remote-tracking refs named `AAA_*.txt`.

---

## Step 0 — Diagnosis (run first, read output before continuing)

```bash
cd ~/hybrid-rsentry

# 1. Find every AAA_ file anywhere in the repo tree (working tree + .git)
find . -name "AAA_*" -not -path "*/node_modules/*" 2>/dev/null

# 2. Check if any AAA_ refs exist in packed-refs too
grep "AAA_" .git/packed-refs 2>/dev/null || echo "none in packed-refs"

# 3. Check if any AAA_ branches exist on GitHub remote
git ls-remote origin | grep "AAA_"

# 4. Confirm current WATCH_PATH in .env
grep WATCH_PATH .env

# 5. Check whether WATCH_PATH is accidentally inside the repo directory
python3 -c "
import os, pathlib
watch = os.getenv('WATCH_PATH', '')
repo = str(pathlib.Path.home() / 'hybrid-rsentry')
if watch.startswith(repo):
    print(f'DANGER: WATCH_PATH={watch} is INSIDE the git repo at {repo}')
else:
    print(f'OK: WATCH_PATH={watch} is outside the repo')
"
```

Record the output. Share it before proceeding if anything is unexpected.

---

## Step 1 — Immediate Cleanup (local + remote)

### 1a. Remove AAA_ files from local `.git/refs/`

```bash
cd ~/hybrid-rsentry

# Remove from all ref subdirectories
find .git/refs -name "AAA_*" -type f -delete
echo "Removed from .git/refs"

# Remove from packed-refs if present
if grep -q "AAA_" .git/packed-refs 2>/dev/null; then
    cp .git/packed-refs .git/packed-refs.bak
    grep -v "AAA_" .git/packed-refs > .git/packed-refs.tmp
    mv .git/packed-refs.tmp .git/packed-refs
    echo "Removed from packed-refs (backup at .git/packed-refs.bak)"
else
    echo "packed-refs: nothing to remove"
fi
```

### 1b. Delete AAA_ branches on GitHub remote (if Step 0 found any)

```bash
# For each branch name found by Step 0 git ls-remote, run:
# git push origin --delete "AAA_<name>"
# Example — adjust to actual names from Step 0 output:
# git push origin --delete "AAA_canary_01.txt"
```

### 1c. Prune stale remote-tracking refs

```bash
git remote prune origin
git fetch --prune
```

### 1d. Verify git is healthy

```bash
git status
git log --oneline -5
```

If these pass without errors, Step 1 is complete.

---

## Step 2 — Code Fix: Guard `adaptive.py` against unsafe paths

**File:** `agent/adaptive.py`

**What to change:** Add a `_is_safe_target()` method that rejects any target directory that is:
- Inside a `.git` directory (any level deep)
- Inside the project repo root itself (belt-and-suspenders)
- The system root or a known system directory (`/proc`, `/sys`, `/dev`, `/run`)

Edit `adaptive.py`. After the class-level constants (`REPOSITION_THRESHOLD`, `MIN_OBSERVATIONS`)
and before `__init__`, add this helper. Then call it in `reposition()`.

### 2a. Add `_UNSAFE_PREFIXES` constant after line with `MIN_OBSERVATIONS`

```python
# Directories the repositioner must never touch
_UNSAFE_PREFIXES = (
    "/.git/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/run/",
)
```

### 2b. Add `_is_safe_target()` as a static method inside the class

```python
@staticmethod
def _is_safe_target(path: Path) -> bool:
    """Return False for any path that could corrupt system or VCS state."""
    resolved = str(path.resolve()) + "/"
    # Reject anything inside a .git directory (at any depth)
    if "/.git/" in resolved:
        return False
    for prefix in _UNSAFE_PREFIXES:
        if resolved.startswith(prefix):
            return False
    return True
```

### 2c. Modify `reposition()` to call the guard before moving

In the `reposition()` loop, find this block:

```python
        target_dir = Path(hotspots[i % len(hotspots)])
        target_dir.mkdir(parents=True, exist_ok=True)
        new_path = target_dir / canary.name
```

Replace with:

```python
        target_dir = Path(hotspots[i % len(hotspots)])
        if not self._is_safe_target(target_dir):
            logger.warning(
                "Markov: refusing unsafe reposition target %s — skipping", target_dir
            )
            new_paths.append(canary)
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        new_path = target_dir / canary.name
```

---

## Step 3 — Code Fix: Validate WATCH_PATH in `monitor.py`

**File:** `agent/monitor.py`

**What to change:** At startup, before the watchdog observer starts, verify that `WATCH_PATH` is
not inside the git repo directory. If it is, log a critical error and exit immediately rather than
silently creating the corruption condition.

Find the block near the bottom of `monitor.py` where the `Observer` is created and started
(look for `observer = Observer()` or `observer.start()`). Before that block, add:

```python
def _validate_watch_path(watch_path: str) -> None:
    """Refuse to start if WATCH_PATH is inside the git repo (would corrupt .git/refs)."""
    import pathlib
    resolved = pathlib.Path(watch_path).resolve()
    # Walk up looking for a .git directory
    check = resolved
    for _ in range(10):  # max 10 levels up
        if (check / ".git").is_dir():
            logger.critical(
                "WATCH_PATH=%s is inside a git repository at %s. "
                "This will corrupt .git/refs via canary file placement. "
                "Set WATCH_PATH to a directory outside the repo and restart.",
                watch_path, check,
            )
            sys.exit(1)
        parent = check.parent
        if parent == check:
            break
        check = parent
```

Then call it early in the `main()` function (or whatever the entry point is) before the Observer
is created:

```python
_validate_watch_path(WATCH_PATH)
```

---

## Step 4 — Add `.gitignore` entries

**File:** `.gitignore` (repo root)

Open `.gitignore` and add the following block. If a canary-related section already exists, add
these lines there. Otherwise append at the end:

```
# Canary files — never track these in git
AAA_*.txt
**/AAA_*.txt
```

This prevents a `git add .` from ever staging a canary file, which in turn prevents a push from
creating remote-tracking refs named `AAA_*.txt`.

---

## Step 5 — Add a Git Hook (`post-merge`) for automatic cleanup

This hook runs automatically after every `git pull` (which is internally a fetch + merge) and
removes any stray AAA_ files from `.git/refs/`.

```bash
cat > ~/hybrid-rsentry/.git/hooks/post-merge << 'EOF'
#!/usr/bin/env bash
# post-merge hook — remove canary files that leaked into .git/refs/
FOUND=$(find "$(git rev-parse --git-dir)/refs" -name "AAA_*" 2>/dev/null)
if [ -n "$FOUND" ]; then
    echo "[post-merge hook] Removing canary ref corruption:"
    echo "$FOUND"
    find "$(git rev-parse --git-dir)/refs" -name "AAA_*" -delete
fi
EOF
chmod +x ~/hybrid-rsentry/.git/hooks/post-merge
```

Also add a `pre-fetch` hook so cleanup runs before the fetch phase of a pull:

```bash
cat > ~/hybrid-rsentry/.git/hooks/pre-auto-gc << 'EOF'
#!/usr/bin/env bash
find "$(git rev-parse --git-dir)/refs" -name "AAA_*" -delete 2>/dev/null
exit 0
EOF
chmod +x ~/hybrid-rsentry/.git/hooks/pre-auto-gc
```

And a convenience alias so the team can do `git safe-pull` instead of the manual fix:

```bash
git config alias.safe-pull '!find .git/refs -name "AAA_*" -delete 2>/dev/null; git pull'
```

---

## Step 6 — Commit and Push All Changes

```bash
cd ~/hybrid-rsentry

git add agent/adaptive.py agent/monitor.py .gitignore
git commit -m "fix: prevent canary files from corrupting .git/refs

- adaptive.py: _is_safe_target() blocks repositioning into .git, /proc, /sys
- monitor.py: _validate_watch_path() exits immediately if WATCH_PATH is inside a git repo
- .gitignore: AAA_*.txt excluded so canaries can never be staged or pushed"

git push origin main
```

---

## Step 7 — Verification

### 7a. Confirm the agent starts cleanly

```bash
cd ~/hybrid-rsentry
set -a && source .env && set +a
sudo -E ~/hybrid-rsentry/venv/bin/python -m agent.monitor
```

Expected: no errors, normal startup logs.

### 7b. Confirm git commands work without manual cleanup

```bash
git pull
git status
git log --oneline -3
```

Expected: no `fatal: bad object` errors.

### 7c. Confirm the path guard triggers (optional — test in a throwaway branch)

```bash
# Temporarily set WATCH_PATH to inside the repo and start the agent
# Expected: agent logs CRITICAL and exits immediately
WATCH_PATH=~/hybrid-rsentry sudo -E ~/hybrid-rsentry/venv/bin/python -m agent.monitor
# Restore: WATCH_PATH is read from .env, so just restart normally
```

### 7d. Confirm the repositioner guard fires in logs

Trigger a reposition by waiting for `REPOSITION_INTERVAL` seconds with the agent running, then
check agent logs for any `refusing unsafe reposition target` lines. If `.git` directories never
scored as hotspots (because WATCH_PATH is correctly outside the repo), no such lines will appear —
that is also correct.

---

## Step 8 — Update CLAUDE.md

In `CLAUDE.md`, under **Known issues and fixes**, replace the canary entry:

**Old:**
```
**Canary files appear in `.git/refs/heads/`**
Symptom: git commands error; files named `AAA_*.txt` inside `.git/refs/`.
Fix: `find .git/refs -name "AAA_*" -delete`
```

**New:**
```
**Canary files appear in `.git/refs/heads/`** (should not recur after fix in adaptive.py)
Symptom: git commands error with `fatal: bad object refs/remotes/origin/AAA_*.txt`.
Root cause: Markov repositioner moved canaries into .git/ (no longer possible after path guard).
Emergency fix (if it somehow recurs): `git safe-pull` (alias added by fix plan), or
  `find .git/refs -name "AAA_*" -delete && git pull`
Permanent fix: see docs/canary-git-fix-plan.md — already applied.
```

---

## Files Modified Summary

| File | Change |
|---|---|
| `agent/adaptive.py` | Add `_UNSAFE_PREFIXES`, `_is_safe_target()`, guard in `reposition()` |
| `agent/monitor.py` | Add `_validate_watch_path()`, call it before Observer starts |
| `.gitignore` | Add `AAA_*.txt` and `**/AAA_*.txt` |
| `.git/hooks/post-merge` | Auto-cleanup hook (local only, not committed) |
| `.git/hooks/pre-auto-gc` | Pre-GC cleanup hook (local only) |
| `CLAUDE.md` | Update known issues section |

> Git hooks live in `.git/hooks/` which is not tracked by git. Each developer cloning the repo
> must re-run the Step 5 hook commands. Consider adding them to `setup.sh` if AJahmadcyber also
> needs them on his machine.
