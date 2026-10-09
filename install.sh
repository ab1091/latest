#!/bin/bash
# AllZone Voice Bot — Bootstrap script
# Run this ONCE on a new machine: bash install.sh

set -e

G="\033[92m"; Y="\033[93m"; R="\033[91m"; B="\033[94m"; W="\033[97m"; NC="\033[0m"

ok()   { echo -e "  ${G}✓${NC}  $1"; }
info() { echo -e "  ${B}→${NC}  $1"; }
warn() { echo -e "  ${Y}!${NC}  $1"; }
fail() { echo -e "  ${R}✗${NC}  $1"; exit 1; }

echo -e "\n${B}══════════════════════════════════════════════════════${NC}"
echo -e "${B}   AllZone Voice Bot — New Machine Bootstrap${NC}"
echo -e "${B}══════════════════════════════════════════════════════${NC}\n"

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    ok "Homebrew installed"
else
    ok "Homebrew found"
fi

# ── 2. Python 3 ───────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    info "Installing Python 3..."
    brew install python
    ok "Python 3 installed"
else
    ok "Python 3 found"
fi

# ── 3. Node.js / npm ─────────────────────────────────────────────────────────
if ! command -v npm &>/dev/null; then
    info "Installing Node.js..."
    brew install node
    ok "Node.js installed"
else
    ok "Node.js found"
fi

# ── 4. Docker Desktop ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Installing Docker Desktop..."
    brew install --cask docker
    echo ""
    warn "Docker Desktop installed. Please:"
    warn "  1. Open Docker Desktop from Applications"
    warn "  2. Complete the setup wizard"
    warn "  3. Wait for Docker to start (whale icon in menu bar)"
    warn "  4. Then run: python3 setup.py"
    exit 0
else
    ok "Docker found"
fi

# ── 5. Check .env ────────────────────────────────────────────────────────────
echo ""
if [[ ! -f "ai-service/.env" ]]; then
    warn "ai-service/.env not found!"
    warn "Copy your .env file to ai-service/.env before continuing."
    warn "Then run: python3 setup.py"
    exit 0
fi

# ── 6. Run main setup ────────────────────────────────────────────────────────
echo ""
ok "All prerequisites ready — starting setup..."
echo ""
python3 setup.py
