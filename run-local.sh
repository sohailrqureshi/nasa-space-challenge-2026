#!/usr/bin/env bash
# SELENE SCOUT — Local Development Launcher
# Usage:  ./run-local.sh
#
# Starts the FastAPI backend (which also serves the pre-built React frontend)
# at http://localhost:8080.  Optionally rebuilds the frontend first.
#
# Prerequisites:
#   - Python 3.11+ with a .venv at project root  (python3 -m venv .venv)
#   - Node.js 18+ with npm (for frontend build)
#   - gcloud ADC configured: gcloud auth application-default login
#     OR a GEMINI_API_KEY set in .env
#   - Internet access for JPL Horizons ephemeris fetch at startup (~10 s)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[selene]${NC} $*"; }
warn()  { echo -e "${YELLOW}[selene]${NC} $*"; }
error() { echo -e "${RED}[selene]${NC} $*" >&2; exit 1; }

# ── 1. Python virtual environment ─────────────────────────────────────────────
if [[ ! -d .venv ]]; then
  info "Creating Python virtual environment…"
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

info "Installing / verifying Python dependencies…"
pip install -q -r requirements.txt

# ── 2. Build React frontend (only if dist/ is missing or stale) ───────────────
FRONTEND_DIR="frontend"
DIST_DIR="$FRONTEND_DIR/dist"

if [[ "${REBUILD_FRONTEND:-0}" == "1" ]] || [[ ! -d "$DIST_DIR" ]]; then
  if ! command -v node &>/dev/null; then
    warn "Node.js not found — skipping frontend build (using existing dist/)"
  else
    info "Building React + CesiumJS frontend…"
    pushd "$FRONTEND_DIR" > /dev/null
    npm install --silent
    npm run build
    popd > /dev/null
    info "Frontend built → $DIST_DIR"
  fi
else
  info "Using existing frontend build at $DIST_DIR"
  info "  (set REBUILD_FRONTEND=1 to force a rebuild)"
fi

# ── 3. Verify .env exists ─────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  warn ".env not found — copying .env.example"
  if [[ -f .env.example ]]; then
    cp .env.example .env
  else
    cat > .env <<'ENVEOF'
# Google Cloud project for Vertex AI / Gemini
GCP_PROJECT=your-gcp-project-id
GCP_LOCATION=global
# Optional: direct Gemini API key (overrides Vertex AI)
# GEMINI_API_KEY=your-key-here
PORT=8080
ENVEOF
    warn "Created placeholder .env — edit with your GCP_PROJECT or GEMINI_API_KEY"
  fi
fi

# ── 4. Launch FastAPI ─────────────────────────────────────────────────────────
PORT="${PORT:-8080}"
info "Starting SELENE SCOUT on http://localhost:${PORT} …"
info ""
info "  Briefing overlay → start exploring → type a command or pick a preset"
info "  Run tests:  pytest tests/ -v"
info ""

exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload \
  --log-level info
