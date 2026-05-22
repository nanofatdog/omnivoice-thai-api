#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  OmniVoice Thai API — One-Line Installer
#  Zero-shot Thai TTS with Web UI + REST API
# ═══════════════════════════════════════════════════════════════
#
#  Host:   curl -fsSL https://raw.../install.sh | bash
#  Docker: RUN bash install.sh --docker
#
set -euo pipefail

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; B='\033[1m'; N='\033[0m'
ok()  { echo -e "${G}[✓]${N} $*"; }
inf() { echo -e "${C}[i]${N} $*"; }
die() { echo -e "\033[0;31m[✗] $*\033[0m"; exit 1; }

DOCKER=false
[[ "${1:-}" == "--docker" ]] && DOCKER=true

MODEL_DIR="${OMNIVOICE_MODEL_DIR:-$HOME/omnivoice-thai}"
PORT="${OMNIVOICE_PORT:-7860}"
HOST="${OMNIVOICE_HOST:-0.0.0.0}"
PYTHON=$(command -v python3 || echo "python3")

echo -e "${C}"
echo "╔══════════════════════════════════════════╗"
echo "║   🎙️  OmniVoice Thai API — Installer     ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${N}"

# ── 1. System check (skip in Docker) ─────────
if $DOCKER; then
    inf "Step 1/4: Docker mode — skipping system checks"
else
    inf "Step 1/5: Checking system..."
    [ -x "$(command -v python3)" ] || die "python3 not found. Install: apt install python3"
    PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
    PYMAJ=$(echo "$PYVER" | cut -d. -f1); PYMIN=$(echo "$PYVER" | cut -d. -f2)
    { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -ge 9 ]; } || die "Python 3.9+ required (found $PYVER)"
    ok "Python $PYVER"
    DISK=$(df -BG "$HOME" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo "0")
    [ "$DISK" -lt 8 ] && die "Need 8GB+ free disk (have ${DISK}GB)"
    ok "Disk: ${DISK}GB free"
fi

# ── 2. Install dependencies ─────────────────
STEP=2; $DOCKER && STEP=2
inf "Step $STEP/5: Installing Python packages..."

$PYTHON -m pip install --quiet --upgrade pip 2>/dev/null || true

# PyTorch with CUDA
if ! $PYTHON -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    inf "Installing PyTorch + CUDA..."
    $PYTHON -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
fi
ok "PyTorch ready"

$PYTHON -m pip install --quiet \
    "huggingface_hub[cli]" \
    omnivoice \
    fastapi \
    "uvicorn[standard]" \
    soundfile \
    python-multipart
ok "Python packages installed"

# ── 3. Download model ───────────────────────
STEP=3; $DOCKER && STEP=3
inf "Step $STEP/5: Downloading model (~4.4GB)..."

if [ -f "$MODEL_DIR/model.safetensors" ]; then
    ok "Model already exists: $MODEL_DIR"
else
    inf "hf download hotdogs/omnivoice-thai --local-dir $MODEL_DIR"
    hf download hotdogs/omnivoice-thai --local-dir "$MODEL_DIR"
    [ -f "$MODEL_DIR/model.safetensors" ] || die "Download failed"
    ok "Model downloaded: $(du -sh "$MODEL_DIR" | cut -f1)"
fi

# ── 4. Get server script (skip in Docker) ───
if $DOCKER; then
    inf "Step 4/4: Docker mode — server.py from build context"
else
    inf "Step 4/5: Getting server.py..."
    SERVER_URL="https://raw.githubusercontent.com/nanofatdog/omnivoice-thai-api/main/server.py"
    curl -fsSL "$SERVER_URL" -o "$MODEL_DIR/server.py"
    chmod +x "$MODEL_DIR/server.py"
    ok "server.py → $MODEL_DIR/server.py"

    cat > "$MODEL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
export OMNIVOICE_MODEL_PATH="$(dirname "$0")"
exec python3 server.py
EOF
    chmod +x "$MODEL_DIR/start.sh"
fi

# ── 5. Start server (skip in Docker) ────────
if $DOCKER; then
    ok "Docker build complete — server will start via CMD"
    exit 0
fi

inf "Step 5/5: Starting server..."

pkill -f "server.py" 2>/dev/null || true
sleep 1

cd "$MODEL_DIR"
nohup python3 server.py > server.log 2>&1 &
PID=$!

inf "Loading model into GPU..."
for i in $(seq 1 60); do
    if curl -sf "http://${HOST}:${PORT}/api/health" > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

HEALTH=$(curl -sf "http://${HOST}:${PORT}/api/health" 2>/dev/null || echo '{}')
VRAM=$(echo "$HEALTH" | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('vram_used_gb','?'))" 2>/dev/null || echo "?")

echo ""
echo -e "${G}${B}╔══════════════════════════════════════════╗${N}"
echo -e "${G}${B}║          🎉  Installation Complete!      ║${N}"
echo -e "${G}${B}╚══════════════════════════════════════════╝${N}"
echo ""
echo -e "  ${B}Web UI:${N}  http://${HOST}:${PORT}"
echo -e "  ${B}Health:${N}  http://${HOST}:${PORT}/api/health"
echo -e "  ${B}VRAM:${N}   ${VRAM} GB  |  ${B}PID:${N} ${PID}"
echo -e "  ${B}Log:${N}    ${MODEL_DIR}/server.log"
echo ""
echo -e "  ${B}Quick test:${N}"
echo "  curl -X POST http://${HOST}:${PORT}/api/generate \\"
echo "    -F 'text=สวัสดีครับ' -F 'mode=auto' -o test.wav"
echo ""
echo -e "  ${B}Stop:${N}   pkill -f server.py"
echo -e "  ${B}Start:${N}  bash ${MODEL_DIR}/start.sh"
