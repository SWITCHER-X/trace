#!/usr/bin/env bash
# Trace — One-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/your-username/trace/main/install.sh | bash

set -euo pipefail

# ─── Colors & Styles ──────────────────────────────────────────────────────
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly NC='\033[0m' # No Color

# ─── Helpers ──────────────────────────────────────────────────────────────
info()    { printf "${BLUE}ℹ${NC} %s\n" "$*"; }
ok()      { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
error()   { printf "${RED}✗${NC} %s\n" "$*"; }
step()    { printf "\n${BOLD}%s${NC}\n" "$*"; }
run()     { printf "${DIM}$ %s${NC}\n" "$*"; "$@"; }

# ─── Config ───────────────────────────────────────────────────────────────
REPO="your-username/trace"
BRANCH="main"
INSTALL_DIR="${HOME}/.local/bin"
PYTHON_MIN_VERSION="3.8"
VENV_DIR="${HOME}/.local/share/trace-venv"

# ─── Main ─────────────────────────────────────────────────────────────────
main() {
    clear
    cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║  Trace — Universal File Metadata & Privacy Inspector          ║
║  Installer                                                    ║
╚══════════════════════════════════════════════════════════════╝
EOF

    # 1. Check Python
    step "Checking Python..."
    if ! command -v python3 >/dev/null; then
        error "Python 3 not found. Install Python 3.8+ first."
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"; then
        error "Python ${PYTHON_VERSION} found, but ${PYTHON_MIN_VERSION}+ required."
        exit 1
    fi
    ok "Python ${PYTHON_VERSION} ✓"

    # 2. Check pip
    step "Checking pip..."
    if ! python3 -m pip --version >/dev/null 2>&1; then
        warn "pip not found, installing via ensurepip..."
        python3 -m ensurepip --upgrade
    fi
    ok "pip ✓"

    # 3. Create virtual environment
    step "Setting up virtual environment..."
    if [[ -d "${VENV_DIR}" ]]; then
        info "Virtual environment exists at ${VENV_DIR}"
    else
        run python3 -m venv "${VENV_DIR}"
        ok "Virtual environment created"
    fi

    # 4. Upgrade pip in venv
    step "Upgrading pip..."
    run "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel >/dev/null
    ok "pip upgraded"

    # 5. Install trace
    step "Installing Trace..."
    # Determine source directory
    if [[ -f "pyproject.toml" ]] && grep -q "trace-metadata" pyproject.toml 2>/dev/null; then
        SRC_DIR="."
    elif [[ -f "trace/pyproject.toml" ]] && grep -q "trace-metadata" trace/pyproject.toml 2>/dev/null; then
        SRC_DIR="trace"
    elif [[ -d ".git" ]] && git remote get-url origin 2>/dev/null | grep -q "${REPO}"; then
        SRC_DIR="."
    else
        SRC_DIR=""
    fi

    if [[ -n "${SRC_DIR}" ]]; then
        # Installing from local source
        info "Installing from local source (${SRC_DIR})..."
        run "${VENV_DIR}/bin/pip" install -e "${SRC_DIR}[web]"
    else
        # Install from GitHub
        info "Installing from GitHub (${REPO}@${BRANCH})..."
        run "${VENV_DIR}/bin/pip" install "trace-metadata[web] @ git+https://github.com/${REPO}.git@${BRANCH}"
    fi
    ok "Trace installed"

    # 6. Ensure install directory exists
    step "Setting up PATH..."
    mkdir -p "${INSTALL_DIR}"

    # 7. Create wrapper scripts
    cat > "${INSTALL_DIR}/trace" << WRAPPER
#!/usr/bin/env bash
# Trace CLI wrapper
exec "${VENV_DIR}/bin/trace" "\$@"
WRAPPER

    cat > "${INSTALL_DIR}/trace-web" << WRAPPER
#!/usr/bin/env bash
# Trace Web GUI wrapper
exec "${VENV_DIR}/bin/trace-web" "\$@"
WRAPPER

    chmod +x "${INSTALL_DIR}/trace" "${INSTALL_DIR}/trace-web"
    ok "Wrapper scripts created in ${INSTALL_DIR}"

    # 8. PATH check
    step "Verifying PATH..."
    if [[ ":${PATH}:" != *":${INSTALL_DIR}:"* ]]; then
        warn "${INSTALL_DIR} is not in your PATH"
        echo ""
        echo "Add this to your shell config (~/.bashrc, ~/.zshrc, ~/.config/fish/config.fish):"
        echo ""
        echo "    export PATH=\"\${HOME}/.local/bin:\${PATH}\""
        echo ""
        echo "Then restart your shell or run: source ~/.bashrc"
    else
        ok "${INSTALL_DIR} is in PATH"
    fi

    # 9. Verify installation
    step "Verifying installation..."
    if "${INSTALL_DIR}/trace" --help >/dev/null 2>&1; then
        ok "trace command works"
    else
        error "trace command failed. Check PATH."
        exit 1
    fi

    if "${INSTALL_DIR}/trace-web" --help >/dev/null 2>&1; then
        ok "trace-web command works"
    else
        warn "trace-web may need Flask (try: pip install -e '.[web]')"
    fi

    # 10. Success
    echo ""
    cat << EOF
${GREEN}╔══════════════════════════════════════════════════════════════╗
║  Installation complete!                                       ║
╚══════════════════════════════════════════════════════════════╝${NC}

${BOLD}Quick start:${NC}

  ${CYAN}# Scan a file${NC}
  trace scan photo.jpg

  ${CYAN}# Scan with JSON output${NC}
  trace scan photo.jpg --json

  ${CYAN}# Scrub metadata (creates photo_clean.jpg)${NC}
  trace scrub photo.jpg

  ${CYAN}# Launch web GUI${NC}
  trace-web
  # → Open http://localhost:5001 in your browser

${BOLD}Documentation:${NC}
  https://github.com/${REPO}

${BOLD}Issues:${NC}
  https://github.com/${REPO}/issues

${DIM}Tip: Add \${HOME}/.local/bin to your PATH if not already there.${NC}
EOF
}

# Run main
main "$@"