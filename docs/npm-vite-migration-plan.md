# npm Dependabot Alerts — CRA → Vite Migration Plan

**For Claude Code to execute on Kali (`~/hybrid-rsentry/frontend`)**  
**Created: 2026-05-26**  
**Companion to:** `docs/canary-git-fix-plan.md` (unrelated — do either plan in any order, they do not touch the same files)

---

## Background

`react-scripts 5.0.1` is the last version of Create React App (CRA). It is abandoned upstream and
pins old versions of webpack, jest, svgo, workbox, and other build tools. This causes **28 npm
audit vulnerabilities** (13 HIGH, 6 MODERATE, 9 LOW) that cannot be fixed while staying on CRA —
`npm audit fix --force` would install `react-scripts@0.0.0` and destroy the frontend build.

**All 28 vulnerabilities are in build-toolchain packages, not in the production JavaScript bundle.**
They do not affect users visiting the dashboard. However they are real risks for the developer
machine (e.g., `webpack-dev-server` can expose source code to a malicious website, `serialize-javascript`
RCE during build if inputs are compromised). Eliminating them is correct.

**Solution: migrate from CRA to Vite.** Vite is the modern replacement for CRA. It uses a
completely different toolchain (Rollup + esbuild instead of webpack), so all 28 vulnerabilities
disappear. All existing React components, pages, Tailwind CSS, Recharts, jsPDF, WebSocket logic —
everything stays exactly as written. Only the build infrastructure changes.

---

## Pre-flight check

Run these on Kali before starting. They must all pass.

```bash
cd ~/hybrid-rsentry/frontend

# 1. Confirm current audit count (expect 28)
npm audit 2>/dev/null | tail -5

# 2. Confirm the app currently starts (sanity check)
# If it's already running, skip this; just confirm http://localhost:3000 loads
BROWSER=none npm start &
sleep 15
curl -s http://localhost:3000 | grep -q "html" && echo "CRA: OK" || echo "CRA: FAILED"
kill %1 2>/dev/null

# 3. Check Node version (need >= 18)
node --version

# 4. Confirm current package.json is clean
cat package.json | python3 -m json.tool > /dev/null && echo "JSON valid" || echo "JSON BROKEN — stop here"
```

If the CRA start fails in step 2, note the error and fix it before migrating — the migration does
not fix pre-existing runtime bugs.

---

## Step 1 — Install Vite and Remove react-scripts

```bash
cd ~/hybrid-rsentry/frontend

# Install Vite + React plugin (save as devDependencies)
npm install --save-dev vite @vitejs/plugin-react

# Install autoprefixer (PostCSS companion to Tailwind — not bundled by CRA anymore)
npm install --save-dev autoprefixer

# Remove react-scripts completely
npm uninstall react-scripts
```

After this step `npm audit` will already drop significantly. Continue regardless.

---

## Step 2 — Create `vite.config.js`

Create this file at `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
```

> The `proxy` config here replaces the `"proxy": "http://localhost:8000"` field that was in
> `package.json`. Both `/api` routes and WebSocket `/ws` routes are proxied to the FastAPI backend.

---

## Step 3 — Create `postcss.config.cjs`

Tailwind CSS requires PostCSS. CRA wired this up internally. Vite needs an explicit config file.

Create `frontend/postcss.config.cjs`:

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

> Use `.cjs` extension because `tailwind.config.js` uses CommonJS (`module.exports`) and
> keeping PostCSS in the same module format avoids ESM/CJS conflicts.

---

## Step 4 — Update `package.json`

Open `frontend/package.json`. Make these exact changes:

### 4a. Replace the `scripts` block

**Old:**
```json
"scripts": {
  "start": "react-scripts start",
  "build": "react-scripts build",
  "test": "react-scripts test",
  "eject": "react-scripts eject"
},
```

**New:**
```json
"scripts": {
  "dev": "vite",
  "start": "vite",
  "build": "vite build",
  "preview": "vite preview"
},
```

> `"start": "vite"` is kept as an alias so any existing script or teammate muscle memory still
> works. The canonical dev command is `npm run dev`.

### 4b. Remove the `proxy` field

Delete this line entirely:
```json
"proxy": "http://localhost:8000"
```

Vite handles this via `vite.config.js` (Step 2). Leaving this field in would have no effect but
could confuse future contributors.

### 4c. Remove the `eslintConfig` block

Delete:
```json
"eslintConfig": {
  "extends": [
    "react-app",
    "react-app/jest"
  ]
},
```

The `react-app` ESLint config is part of `react-scripts`. With CRA removed it no longer resolves.
ESLint can be re-added later with a separate `.eslintrc.js` if wanted.

### 4d. Remove the `browserslist` block

Delete the entire `browserslist` field. Vite targets modern browsers by default and does not use
this field. If you need a custom browserslist in the future, set `build.target` in `vite.config.js`.

---

## Step 5 — Move and Update `index.html`

Vite expects `index.html` at the project root (i.e., `frontend/index.html`), not inside `public/`.

```bash
# Move it up one level
mv ~/hybrid-rsentry/frontend/public/index.html ~/hybrid-rsentry/frontend/index.html

# Remove the now-empty public directory (only had index.html)
rmdir ~/hybrid-rsentry/frontend/public
```

Now open `frontend/index.html` and add the Vite module script tag inside `<body>`, just before
`</body>`:

```html
<script type="module" src="/src/index.jsx"></script>
```

The final `index.html` should look like this:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#030712" />
    <meta name="description" content="Hybrid R-Sentry — Ransomware Detection Dashboard" />
    <title>Hybrid R-Sentry</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <noscript>You need JavaScript to run Hybrid R-Sentry.</noscript>
    <div id="root"></div>
    <script type="module" src="/src/index.jsx"></script>
  </body>
</html>
```

---

## Step 6 — Rename `src/index.js` to `src/index.jsx`

Vite does not process JSX in `.js` files by default. The entry point uses JSX (`<React.StrictMode>`).

```bash
mv ~/hybrid-rsentry/frontend/src/index.js ~/hybrid-rsentry/frontend/src/index.jsx
```

File content is unchanged — just the extension.

---

## Step 7 — Update Environment Variable References

CRA uses `process.env.REACT_APP_*`. Vite uses `import.meta.env.VITE_*`. There are exactly
**4 occurrences** across 4 files. Edit each one:

### `src/api/client.js` — line 3

**Old:**
```js
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
```
**New:**
```js
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

### `src/components/AIAnalystPanel.jsx` — line 5

**Old:**
```js
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
```
**New:**
```js
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

### `src/hooks/useWebSocket.js` — line 3

**Old:**
```js
const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';
```
**New:**
```js
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
```

### `src/pages/AIAnalystPage.jsx` — line 5

**Old:**
```js
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
```
**New:**
```js
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

> **Important:** All 4 env vars have hardcoded fallbacks (`|| 'http://localhost:8000'`).
> This means the app works out-of-the-box with no `.env` file changes required. The env var
> names only matter if someone explicitly sets `VITE_API_URL` or `VITE_WS_URL` in a `.env.local`
> file. The `.env` at the repo root is for the backend — it does not affect the frontend build.

---

## Step 8 — Update `start.sh`

Open `start.sh` at the repo root. Find the frontend section (around line 66):

**Old:**
```bash
echo "==> [5/5] Starting frontend (npm start)..."
cd "$REPO_DIR/frontend"
BROWSER=none npm start &> /tmp/rsentry-frontend.log &
```

**New:**
```bash
echo "==> [5/5] Starting frontend (Vite)..."
cd "$REPO_DIR/frontend"
npm run dev &> /tmp/rsentry-frontend.log &
```

> `BROWSER=none` was a CRA flag to suppress auto-opening a browser tab. Vite does not open a
> browser by default, so the flag is not needed. `npm run dev` maps to `vite` via package.json.

---

## Step 9 — Run `npm install` to Regenerate the Lock File

```bash
cd ~/hybrid-rsentry/frontend
npm install
```

This regenerates `package-lock.json` without `react-scripts` and all its vulnerable transitive
dependencies. This is the step that actually eliminates the 28 vulnerabilities.

---

## Step 10 — Verify

### 10a. Audit check

```bash
cd ~/hybrid-rsentry/frontend
npm audit
```

Expected result: **0 vulnerabilities**. If any remain, check `npm audit --json` to identify which
package and whether it is a runtime or devDependency.

### 10b. Dev server starts

```bash
cd ~/hybrid-rsentry/frontend
npm run dev
```

Expected:
```
  VITE v5.x.x  ready in Xms

  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
```

Open `http://localhost:3000` in a browser and confirm:
- Dashboard loads (Overview page with stat cards)
- No console errors
- Sidebar navigation works for all 6 pages (Overview, Alerts, Hosts, Filesystem, AI Analyst, Reports)

### 10c. Backend API calls work

With the FastAPI backend running (`uvicorn`), verify the proxy works:

```bash
# From a different terminal — confirm the frontend proxies API calls correctly
curl http://localhost:3000/api/alerts/counts
# Should return JSON like {"CRITICAL":0,"HIGH":0,"MEDIUM":0}
# (not a 404 or HTML page)
```

### 10d. WebSocket connects

Open the dashboard. Check the bottom-left status indicator shows a green dot (connected).
If it shows red (disconnected), check the browser console for WebSocket errors.

### 10e. Production build works

```bash
cd ~/hybrid-rsentry/frontend
npm run build
ls dist/
```

Expected: `dist/` folder created with `index.html`, `assets/` containing JS/CSS bundles.
No errors during the build.

### 10f. Run `bash test_event.sh` end-to-end

With all 5 services running (use `bash start.sh`), run the pipeline test:

```bash
cd ~/hybrid-rsentry
bash test_event.sh
```

Expected:
- Terminal shows CANARY_TOUCHED event sent
- Dashboard shows CRITICAL alert appear on Overview and Alerts pages
- AI Analyst page shows analysis card appear within ~30 seconds
- No frontend console errors throughout

---

## Step 11 — Commit and Push

```bash
cd ~/hybrid-rsentry

git add \
  frontend/package.json \
  frontend/package-lock.json \
  frontend/vite.config.js \
  frontend/postcss.config.cjs \
  frontend/index.html \
  frontend/src/index.jsx \
  frontend/src/api/client.js \
  frontend/src/components/AIAnalystPanel.jsx \
  frontend/src/hooks/useWebSocket.js \
  frontend/src/pages/AIAnalystPage.jsx \
  start.sh

# If public/ directory was deleted:
git rm frontend/public/index.html 2>/dev/null || true

git commit -m "fix: migrate frontend from CRA to Vite, eliminating 28 npm audit vulnerabilities

react-scripts 5.0.1 is abandoned and pins vulnerable versions of webpack,
jest, svgo, workbox, and serialize-javascript. Vite uses a clean toolchain
with zero audit findings.

Changes:
- vite.config.js: new build config, proxy /api and /ws to localhost:8000
- postcss.config.cjs: explicit PostCSS config for Tailwind
- index.html: moved from public/ to frontend root, added module script tag
- src/index.js -> src/index.jsx: renamed for Vite JSX processing
- env vars: REACT_APP_* -> import.meta.env.VITE_* (fallbacks unchanged)
- package.json: scripts updated, proxy/eslintConfig/browserslist removed
- start.sh: npm start -> npm run dev"

git push origin main
```

---

## Rollback Plan (if something breaks)

The pre-migration state is preserved in git. To revert:

```bash
cd ~/hybrid-rsentry
git revert HEAD --no-edit
git push origin main
cd frontend && npm install
```

Or to go back to a specific commit:
```bash
git checkout <commit-before-migration> -- frontend/package.json frontend/package-lock.json
npm install
```

---

## Update CLAUDE.md

In `CLAUDE.md`, update the startup sequence section:

**Old line (Terminal 5):**
```
# Terminal 5
cd ~/hybrid-rsentry/frontend && npm start
```

**New:**
```
# Terminal 5
cd ~/hybrid-rsentry/frontend && npm run dev
```

Also update the **Hard rules** section — remove rule #6 which was:
```
6. **Never run `npm audit fix --force`.** It installs `react-scripts@0.0.0` and breaks the frontend build.
```

Replace with:
```
6. **Do not run `npm audit fix --force` without reading the audit output first.** All runtime
   dependencies are clean. Build-tool advisories can be researched before acting.
```

---

## Files Modified Summary

| File | Change |
|---|---|
| `frontend/package.json` | Remove react-scripts, update scripts, remove proxy/eslintConfig/browserslist |
| `frontend/package-lock.json` | Regenerated — no react-scripts, no vulnerable transitive deps |
| `frontend/vite.config.js` | **New** — Vite config with React plugin, port 3000, API/WS proxy |
| `frontend/postcss.config.cjs` | **New** — PostCSS config for Tailwind + autoprefixer |
| `frontend/index.html` | Moved from `public/index.html`, added `<script type="module">` tag |
| `frontend/public/index.html` | **Deleted** (moved to root) |
| `frontend/src/index.jsx` | Renamed from `index.js` (no content change) |
| `frontend/src/api/client.js` | `process.env.REACT_APP_API_URL` → `import.meta.env.VITE_API_URL` |
| `frontend/src/components/AIAnalystPanel.jsx` | Same env var rename |
| `frontend/src/hooks/useWebSocket.js` | `process.env.REACT_APP_WS_URL` → `import.meta.env.VITE_WS_URL` |
| `frontend/src/pages/AIAnalystPage.jsx` | `process.env.REACT_APP_API_URL` → `import.meta.env.VITE_API_URL` |
| `start.sh` | `BROWSER=none npm start` → `npm run dev` |
| `CLAUDE.md` | Update Terminal 5 command, update rule #6 |

**Not changed:**  
All `.jsx` components, pages, hooks, Recharts, jsPDF, Tailwind classes, Sidebar, WebSocket
reconnect logic, AI Analyst state — none of these are touched. The migration is purely
infrastructure.

---

## Relationship to `canary-git-fix-plan.md`

These two plans are **fully independent**. They touch different files and different subsystems:

| | canary-git-fix-plan.md | npm-vite-migration-plan.md |
|---|---|---|
| Files changed | `agent/adaptive.py`, `agent/monitor.py`, `.gitignore`, `.git/hooks/` | `frontend/` tree, `start.sh` |
| Risk area | Git ref corruption from canary files | npm audit vulnerabilities |
| Can run in parallel? | No — do one at a time to keep commits clean | — |
| Order matters? | No — either plan can go first | — |

Do one complete plan including its commit, then start the other.
