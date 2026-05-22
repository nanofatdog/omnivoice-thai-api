FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

# ── Environment ─────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV OMNIVOICE_MODEL_PATH=/app/model
ENV OMNIVOICE_PORT=7860
ENV OMNIVOICE_HOST=0.0.0.0

# ── System packages ─────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libffi-dev \
    liblzma-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# ── Python 3.12 ─────────────────────────────
RUN add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-dev python3.12-venv \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# ── PyTorch (CUDA 12.1) ─────────────────────
RUN python3 -m pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# ── OmniVoice + API deps ────────────────────
RUN python3 -m pip install --no-cache-dir \
    "huggingface_hub[cli]" \
    omnivoice \
    fastapi \
    "uvicorn[standard]" \
    soundfile \
    python-multipart

# ── Download model (~4.4GB) ─────────────────
RUN mkdir -p /app/model /app/outputs \
    && hf download hotdogs/omnivoice-thai --local-dir /app/model

# ── Copy server ─────────────────────────────
COPY server.py /app/server.py
RUN chmod +x /app/server.py

# ── Start script ────────────────────────────
RUN echo '#!/bin/bash\ncd /app\nexport OMNIVOICE_MODEL_PATH=/app/model\nexec python3 server.py' > /app/start.sh \
    && chmod +x /app/start.sh

# ── Expose ──────────────────────────────────
EXPOSE 7860

# ── Health check ────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:7860/api/health || exit 1

# ── Run ─────────────────────────────────────
WORKDIR /app
CMD ["python3", "server.py"]
