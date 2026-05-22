# 🎙️ OmniVoice Thai API

**Zero-shot Thai TTS** — Web UI + REST API for Voice Cloning, Voice Design, and Auto Voice generation.

Powered by [hotdogs/omnivoice-thai](https://huggingface.co/hotdogs/omnivoice-thai) — fine-tuned on 20K Thai utterances (~12.6 hrs).

## ✨ Features

| Mode | Description | Input |
|------|-------------|-------|
| 🎤 **Voice Cloning** | Clone any voice from 3–10s reference audio | `ref_audio` + `text` |
| 🎨 **Voice Design** | Describe voice attributes in natural language | `instruct` + `text` |
| 🤖 **Auto Voice** | Let the model choose the best voice | `text` only |

## 🚀 One-Click Install

```bash
git clone https://github.com/nanofatdog/omnivoice-thai-api.git
cd omnivoice-thai-api
chmod +x install.sh
sudo ./install.sh
```

The installer automatically:
- Checks Python / CUDA / GPU / disk space
- Installs all dependencies
- Downloads the model (~4.4GB) from HuggingFace
- Sets up systemd auto-start (if running as root)
- Starts the server on port `7860`

### Custom options

```bash
# Custom port & model location
OMNIVOICE_PORT=9000 OMNIVOICE_MODEL_DIR=/data/omnivoice ./install.sh

# CPU-only (no CUDA)
OMNIVOICE_AUTO_START=no ./install.sh
```

## 📡 API Reference

### `GET /api/health`

```bash
curl http://localhost:7860/api/health
```

```json
{
  "status": "ok",
  "model_loaded": true,
  "device": "cuda:0",
  "gpu_name": "NVIDIA GeForce RTX 3060",
  "vram_total_gb": 7.7,
  "vram_used_gb": 3.4
}
```

### `POST /api/generate` (form-data)

Generate speech audio — returns WAV file.

**Auto Voice** (no reference):
```bash
curl -X POST http://localhost:7860/api/generate \
  -F "text=สวัสดีครับ วันนี้อากาศดีมาก" \
  -F "mode=auto" \
  -o output.wav
```

**Voice Cloning** (reference audio):
```bash
curl -X POST http://localhost:7860/api/generate \
  -F "text=สวัสดีค่ะ ยินดีที่ได้รู้จัก" \
  -F "mode=clone" \
  -F "ref_audio=@my_voice.wav" \
  -F "ref_text=ข้อความในไฟล์อ้างอิง" \
  -o cloned.wav
```

**Voice Design** (describe voice):
```bash
curl -X POST http://localhost:7860/api/generate \
  -F "text=สวัสดีค่ะ" \
  -F "mode=design" \
  -F "instruct=female, high pitch, warm, cheerful" \
  -o designed.wav
```

### `POST /api/generate/json`

JSON API — returns base64-encoded WAV.

```bash
curl -X POST http://localhost:7860/api/generate/json \
  -H "Content-Type: application/json" \
  -d '{"text":"สวัสดีครับ","mode":"auto"}'
```

```json
{
  "audio_b64": "UklGRiR...",
  "sample_rate": 24000,
  "duration_s": 2.14
}
```

For voice cloning with JSON, include `ref_audio_b64` (base64 of reference WAV).

### Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | ✅ | Text to speak (max 2000 chars) |
| `mode` | string | - | `auto` (default), `clone`, `design` |
| `ref_audio` | file | clone | Reference WAV/MP3/FLAC (3–10s) |
| `ref_text` | string | - | Transcript of ref audio (auto if blank) |
| `instruct` | string | design | Voice description (e.g. "female, warm, slow") |

### Voice Design — Valid Attributes

| Category | Valid Values |
|----------|--------------|
| **Gender** | `female`, `male` |
| **Age** | `child`, `teenager`, `young adult`, `middle-aged`, `elderly` |
| **Pitch** | `very low pitch`, `low pitch`, `moderate pitch`, `high pitch`, `very high pitch` |
| **Accent** | `american accent`, `australian accent`, `british accent`, `canadian accent`, `chinese accent`, `indian accent`, `japanese accent`, `korean accent`, `portuguese accent`, `russian accent` |
| **Style** | `whisper` |

Examples:
```bash
# Young female
curl -X POST http://localhost:7860/api/generate \
  -F "text=สวัสดีค่ะ" -F "mode=design" \
  -F "instruct=female, young adult, high pitch"

# Professional male
curl -X POST http://localhost:7860/api/generate \
  -F "text=ขอแนะนำสินค้าใหม่" -F "mode=design" \
  -F "instruct=male, middle-aged, low pitch"

# Whispering with accent
curl -X POST http://localhost:7860/api/generate \
  -F "text=ความลับอยู่ที่นี่" -F "mode=design" \
  -F "instruct=male, whisper, british accent"
```

> ⚠️ Only attributes from the table above are accepted. Unsupported items (e.g. `cheerful`, `sad`, `deep`) are silently dropped with a server log warning. Chinese attributes (e.g. `女，青年，高音调`) are also supported.

## 🖥️ Web UI

Open `http://localhost:7860` in your browser — 3 tabs for all modes with audio playback and history.

## 📋 Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU VRAM | 4 GB | 8 GB |
| RAM | 8 GB | 16 GB |
| Disk | 8 GB free | 15 GB free |
| Python | 3.9+ | 3.11+ |
| CUDA | 11.8+ | 12.1+ |

CPU-only works but generation takes 30–60 seconds (vs 3–10s on GPU).

## 🛠️ Management

```bash
# Start
bash ~/omnivoice-thai/start.sh

# Stop
pkill -f server.py

# View logs
tail -f ~/omnivoice-thai/server.log

# Systemd
sudo systemctl start omnivoice-thai
sudo systemctl stop omnivoice-thai
sudo systemctl status omnivoice-thai
```

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OMNIVOICE_MODEL_PATH` | `~/omnivoice-thai` | Model directory |
| `OMNIVOICE_PORT` | `7860` | Server port |
| `OMNIVOICE_HOST` | `0.0.0.0` | Bind address |
| `OMNIVOICE_DEVICE` | `cuda:0` | Torch device |

## 📄 License

MIT — see [LICENSE](LICENSE)

## 🙏 Credits

- [OmniVoice](https://github.com/k2-fsa/OmniVoice) by k2-fsa
- [omnivoice-thai](https://huggingface.co/hotdogs/omnivoice-thai) by hotdogs
