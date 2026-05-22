#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  OmniVoice Thai API — One-Click Installer
#  Zero-shot Thai TTS with Web UI + REST API
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
BOLD='\033[1m'

banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════╗"
    echo "║     🎙️  OmniVoice Thai API Installer     ║"
    echo "║     Zero-Shot Thai TTS                   ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗] $*${NC}"; exit 1; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

# ── Config ──────────────────────────────────
MODEL_DIR="${OMNIVOICE_MODEL_DIR:-$HOME/omnivoice-thai}"
HF_REPO="${OMNIVOICE_HF_REPO:-hotdogs/omnivoice-thai}"
PORT="${OMNIVOICE_PORT:-7860}"
HOST="${OMNIVOICE_HOST:-0.0.0.0}"
AUTO_START="${OMNIVOICE_AUTO_START:-yes}"

banner

# ── Step 1: System check ────────────────────
echo ""; info "Step 1/6: Checking system..."

PYTHON=$(command -v python3 || command -v python || echo "")
if [ -z "$PYTHON" ]; then
    fail "Python 3 not found. Install: apt install python3  or  brew install python3"
fi
PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PYMAJOR" -lt 3 ] || ([ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 9 ]); then
    fail "Python 3.9+ required (found $PYVER)"
fi
log "Python $PYVER"

# CUDA check
HAS_CUDA=false
if $PYTHON -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    HAS_CUDA=true
    GPU_NAME=$($PYTHON -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "Unknown")
    VRAM=$($PYTHON -c "import torch; print(int(torch.cuda.get_device_properties(0).total_memory/1024**3))" 2>/dev/null || echo "?")
    log "GPU: $GPU_NAME (${VRAM}GB VRAM)"
else
    warn "No CUDA GPU detected — CPU mode will be very slow (~30-60s per generate)"
    nvidia-smi &>/dev/null && warn "nvidia-smi works but torch CUDA not available. Install: pip install torch --index-url https://download.pytorch.org/whl/cu121" || true
fi

# Disk
DISK_AVAIL=$(df -BG "$HOME" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo "0")
if [ "$DISK_AVAIL" -lt 8 ]; then
    fail "Need 8GB+ free disk (found ${DISK_AVAIL}GB)"
fi
log "Disk: ${DISK_AVAIL}GB available"

# RAM
RAM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo "0")
[ "$RAM_GB" -lt 4 ] && warn "Low RAM: ${RAM_GB}GB (4GB+ recommended)"

# ── Step 2: Python packages ─────────────────
echo ""; info "Step 2/6: Installing Python packages..."

$PYTHON -m pip install --quiet --upgrade pip 2>/dev/null || true

DEPS=(
    "omnivoice"
    "fastapi"
    "uvicorn[standard]"
    "soundfile"
    "python-multipart"
)

# Install torch with CUDA if not present
if ! $PYTHON -c "import torch" 2>/dev/null; then
    info "Installing PyTorch with CUDA..."
    $PYTHON -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
fi

for pkg in "${DEPS[@]}"; do
    pkg_name=$(echo "$pkg" | cut -d'[' -f1)
    if $PYTHON -c "import $pkg_name" 2>/dev/null; then
        log "$pkg already installed"
    else
        info "Installing $pkg..."
        $PYTHON -m pip install "$pkg"
    fi
done

log "All Python packages installed"

# ── Step 3: Download model ──────────────────
echo ""; info "Step 3/6: Downloading OmniVoice Thai model..."

if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/model.safetensors" ]; then
    log "Model already exists: $MODEL_DIR"
else
    info "Downloading $HF_REPO → $MODEL_DIR"
    info "(This is ~4.4GB and may take a few minutes...)"

    mkdir -p "$MODEL_DIR"

    # Use huggingface_hub if available, otherwise wget
    if $PYTHON -c "import huggingface_hub" 2>/dev/null; then
        $PYTHON -c "
from huggingface_hub import snapshot_download
snapshot_download('$HF_REPO', local_dir='$MODEL_DIR', local_dir_use_symlinks=False)
print('Download complete')
"
    else
        $PYTHON -m pip install --quiet huggingface_hub
        $PYTHON -c "
from huggingface_hub import snapshot_download
snapshot_download('$HF_REPO', local_dir='$MODEL_DIR', local_dir_use_symlinks=False)
print('Download complete')
"
    fi

    if [ ! -f "$MODEL_DIR/model.safetensors" ]; then
        fail "Model download failed — check HF repo: $HF_REPO"
    fi

    SIZE=$(du -sh "$MODEL_DIR" | cut -f1)
    log "Model downloaded: $SIZE"
fi

# ── Step 4: Write server script ─────────────
echo ""; info "Step 4/6: Writing server script..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_SRC="${SCRIPT_DIR}/server.py"
SERVER_DST="${MODEL_DIR}/server.py"

if [ -f "$SERVER_SRC" ]; then
    cp "$SERVER_SRC" "$SERVER_DST"
    log "server.py → $SERVER_DST"
elif [ -f "$SERVER_DST" ]; then
    log "server.py already exists"
else
    # Download from GitHub
    info "Downloading server.py from GitHub..."
    curl -fsSL "https://raw.githubusercontent.com/nanofatdog/omnivoice-thai-api/main/server.py" -o "$SERVER_DST" 2>/dev/null || {
        warn "Cannot auto-download server.py — please copy it manually to $SERVER_DST"
    }
fi

# Create start script
cat > "${MODEL_DIR}/start.sh" << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
export OMNIVOICE_MODEL_PATH="$(dirname "$0")"
exec python3 server.py
STARTEOF
chmod +x "${MODEL_DIR}/start.sh"
log "Start script: ${MODEL_DIR}/start.sh"

# ── Step 5: Create systemd service (optional) ─
echo ""; info "Step 5/6: Setting up auto-start..."

SERVICE_FILE="/etc/systemd/system/omnivoice-thai.service"

if [ "$AUTO_START" = "yes" ] && [ "$(id -u)" -eq 0 ]; then
    cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=OmniVoice Thai API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${MODEL_DIR}
Environment="OMNIVOICE_MODEL_PATH=${MODEL_DIR}"
Environment="OMNIVOICE_PORT=${PORT}"
Environment="OMNIVOICE_HOST=${HOST}"
ExecStart=${PYTHON} ${MODEL_DIR}/server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

    systemctl daemon-reload
    systemctl enable omnivoice-thai 2>/dev/null || warn "Cannot enable systemd service"
    log "systemd service: $SERVICE_FILE"
elif [ "$AUTO_START" = "yes" ]; then
    warn "Not running as root — skip systemd service (use crontab @reboot instead)"
fi

# ── Step 6: Start server ────────────────────
echo ""; info "Step 6/6: Starting server..."

# Kill any existing instance
pkill -f "server.py" 2>/dev/null || true
sleep 1

# Start in background
cd "$MODEL_DIR"
nohup $PYTHON server.py > server.log 2>&1 &
PID=$!
sleep 3

# Wait for model to load (up to 120s)
info "Waiting for model to load..."
for i in $(seq 1 40); do
    if curl -sf "http://${HOST}:${PORT}/api/health" > /dev/null 2>&1; then
        break
    fi
    sleep 3
    [ $((i % 5)) -eq 0 ] && info "  still loading... (${i}s)"
done

# Verify
if curl -sf "http://${HOST}:${PORT}/api/health" > /dev/null 2>&1; then
    HEALTH=$(curl -sf "http://${HOST}:${PORT}/api/health")
    VRAM_USED=$(echo "$HEALTH" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('vram_used_gb','?'))" 2>/dev/null || echo "?")
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║   🎉  Installation Complete!             ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Web UI:${NC}  http://${HOST}:${PORT}"
    echo -e "  ${BOLD}Health:${NC}  http://${HOST}:${PORT}/api/health"
    echo -e "  ${BOLD}VRAM:${NC}   ${VRAM_USED} GB"
    echo -e "  ${BOLD}PID:${NC}    ${PID}"
    echo -e "  ${BOLD}Log:${NC}    ${MODEL_DIR}/server.log"
    echo ""
    echo -e "  ${BOLD}Quick test:${NC}"
    echo "  curl -X POST http://${HOST}:${PORT}/api/generate \\"
    echo "    -F 'text=สวัสดีครับ' -F 'mode=auto' -o test.wav"
    echo ""
    echo -e "  ${BOLD}Stop:${NC}  pkill -f server.py"
    echo -e "  ${BOLD}Start:${NC} bash ${MODEL_DIR}/start.sh"
else
    warn "Server may still be loading... check: tail -f ${MODEL_DIR}/server.log"
    warn "Or start manually: cd ${MODEL_DIR} && python3 server.py"
fi
