#!/usr/bin/env python3
"""
OmniVoice Thai API Server
==========================
Zero-shot Thai TTS with Web UI + REST API

Features:
  🎤 Voice Cloning — reference audio + optional transcript
  🎨 Voice Design — describe voice attributes (gender, pitch, style)
  🤖 Auto Voice — no reference needed, one-shot generation

Usage:
  python server.py                      # default: 0.0.0.0:7860
  OMNIVOICE_PORT=9000 python server.py  # custom port
"""

import io
import os
import sys
import uuid
import shutil
import tempfile
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

import torch
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Config ──────────────────────────────────
MODEL_PATH = os.environ.get("OMNIVOICE_MODEL_PATH", "/root/omnivoice-thai")
DEVICE = os.environ.get("OMNIVOICE_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
OUTPUT_DIR = Path(os.environ.get("OMNIVOICE_OUTPUT_DIR", os.path.join(MODEL_PATH, "outputs")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Valid Voice Design Attributes ──────────
VALID_INSTRUCTS_EN = {
    "american accent", "australian accent", "british accent", "canadian accent",
    "child", "chinese accent", "elderly", "female", "high pitch",
    "indian accent", "japanese accent", "korean accent", "low pitch",
    "male", "middle-aged", "moderate pitch", "portuguese accent",
    "russian accent", "teenager", "very high pitch", "very low pitch",
    "whisper", "young adult",
}

def validate_instruct(instruct: str) -> str:
    """Filter unsupported items. Keeps Chinese, drops unknown English."""
    items = [x.strip() for x in instruct.split(",")]
    valid = []
    unsupported = []
    for item in items:
        if not item:
            continue
        lowered = item.lower()
        if lowered in VALID_INSTRUCTS_EN:
            valid.append(item)
        elif any(ord(c) > 127 for c in item):
            valid.append(item)  # pass through Chinese
        else:
            unsupported.append(item)
    cleaned = ", ".join(valid)
    if unsupported:
        print(f"[INSTRUCT] Dropped unsupported: {unsupported} → kept: {valid}")
    return cleaned

app = FastAPI(
    title="OmniVoice Thai API",
    description="Zero-shot Thai TTS — Voice Cloning · Voice Design · Auto Voice",
    version="2.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Model (lazy singleton) ──────────────────
_model = None
_model_loading = False
_model_error = None


def get_model():
    global _model, _model_loading, _model_error
    if _model is not None:
        return _model
    if _model_error:
        raise RuntimeError(f"Model failed to load: {_model_error}")
    _model_loading = True
    try:
        print(f"[LOAD] OmniVoice from {MODEL_PATH} on {DEVICE}...")
        from omnivoice import OmniVoice

        _model = OmniVoice.from_pretrained(MODEL_PATH, device_map=DEVICE, dtype=torch.float16, load_asr=True)
        vram = torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
        print(f"[READY] VRAM: {vram:.1f} GB")
        _model_loading = False
        return _model
    except Exception as e:
        _model_loading = False
        _model_error = str(e)
        traceback.print_exc()
        raise RuntimeError(f"Failed to load model: {e}")


# ── Lifespan ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_model()
    except Exception as e:
        print(f"[STARTUP] Model preload deferred: {e}")
    yield
    print("[SHUTDOWN] OmniVoice API stopped")


app.router.lifespan_context = lifespan


# ── HTML UI ─────────────────────────────────
HTML = """\
<!DOCTYPE html>
<html lang="th">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>OmniVoice Thai — Zero-Shot TTS</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--muted:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--orange:#d2991d;--radius:8px}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;justify-content:center;align-items:flex-start;padding:20px}
.container{max-width:720px;width:100%}
header{text-align:center;padding:30px 0 20px;border-bottom:1px solid var(--border);margin-bottom:24px}
header h1{font-size:1.8em;margin-bottom:6px}
header .sub{color:var(--muted);font-size:.9em}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:16px}
.card h2{font-size:1.1em;margin-bottom:12px}
label{display:block;font-size:.85em;color:var(--muted);margin-bottom:4px}
textarea,input[type=text],select{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);color:var(--text);font-size:.95em;font-family:inherit;margin-bottom:12px;resize:vertical}
textarea:focus,input:focus,select:focus{outline:none;border-color:var(--accent)}
textarea{min-height:80px}
input[type=file]{margin-bottom:8px;font-size:.9em}
.file-info{font-size:.8em;color:var(--muted);margin-bottom:12px}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
button,.btn{padding:10px 20px;border:none;border-radius:var(--radius);font-size:.95em;cursor:pointer;font-weight:600;transition:opacity .2s;display:inline-flex;align-items:center;gap:6px}
button:hover{opacity:.85}
button:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:#238636;color:#fff}
.btn-accent{background:#1f6feb;color:#fff}
.btn-outline{background:transparent;border:1px solid var(--border);color:var(--text)}
.status{padding:10px 14px;border-radius:var(--radius);font-size:.85em;margin-top:12px;display:none}
.status.info{background:#1f6feb22;color:var(--accent);display:block}
.status.ok{background:#23863622;color:var(--green);display:block}
.status.err{background:#f8514922;color:var(--red);display:block}
.audio-player{margin-top:16px}
.audio-player audio{width:100%;margin-top:6px}
.tabs{display:flex;gap:4px;margin-bottom:16px}
.tab{padding:8px 16px;border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;font-size:.85em;background:var(--bg);color:var(--muted)}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.tab-content{display:none}
.tab-content.active{display:block}
.examples{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
.example-tag{padding:4px 10px;border:1px solid var(--border);border-radius:20px;font-size:.78em;cursor:pointer;background:var(--bg);color:var(--muted)}
.example-tag:hover{border-color:var(--accent);color:var(--accent)}
.history{margin-top:12px}
.history-item{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:.85em}
.history-item audio{height:32px;flex:1}
.history-item .ts{color:var(--muted);font-size:.75em;white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75em;font-weight:600}
.badge.clone{background:#1f6feb33;color:var(--accent)}
.badge.design{background:#d2991d33;color:var(--orange)}
.badge.auto{background:#23863633;color:var(--green)}
pre.code{font-size:.8em;color:var(--muted);overflow-x:auto}
</style>
</head>
<body><div class="container">
<header><h1>🎙️ OmniVoice Thai</h1><p class="sub">Zero-Shot TTS — Voice Cloning · Voice Design · Auto Voice</p></header>

<div class="tabs"><div class="tab active" data-tab="clone">🎤 Voice Cloning</div><div class="tab" data-tab="design">🎨 Voice Design</div><div class="tab" data-tab="auto">🤖 Auto Voice</div></div>

<div class="tab-content active" id="tab-clone">
<div class="card"><h2>🎤 Clone Voice from Reference Audio</h2>
<label>📝 Text to speak</label>
<textarea id="text-clone" placeholder="พิมพ์ข้อความที่ต้องการให้พูด...">สวัสดีครับ ยินดีต้อนรับสู่ OmniVoice Thai</textarea>
<label>🎵 Reference audio (WAV/MP3/FLAC, 3–10s)</label>
<input type="file" id="ref-audio" accept="audio/*"><div class="file-info" id="ref-info"></div>
<label>📋 Reference transcript (optional — auto-transcribe if blank)</label>
<input type="text" id="ref-text" placeholder="ถ้าเว้นว่างไว้ ระบบจะถอดเสียงให้อัตโนมัติ">
<div class="btn-row"><button class="btn-primary" onclick="generate('clone')">✨ Generate</button><button class="btn-outline" onclick="clearForm('clone')">🔄 Clear</button></div>
<div class="examples"><span class="example-tag" onclick="setExample('clone','สวัสดีค่ะ ดิฉันชื่อน้องส้มโอ ยินดีที่ได้รู้จักนะคะ')">👧 หญิง</span><span class="example-tag" onclick="setExample('clone','สวัสดีครับ ผมชื่อคุณต้นกล้า วันนี้อากาศดีมากเลยครับ')">👦 ชาย</span><span class="example-tag" onclick="setExample('clone','วันนี้เราจะมาเรียนรู้เกี่ยวกับปัญญาประดิษฐ์ ประเภทต่างๆ และการประยุกต์ใช้งาน')">📚 วิชาการ</span></div>
</div></div>

<div class="tab-content" id="tab-design">
<div class="card"><h2>🎨 Design Voice by Description</h2>
<label>📝 Text to speak</label>
<textarea id="text-design" placeholder="พิมพ์ข้อความ...">สวัสดีค่ะ การออกแบบเสียงด้วยข้อความเป็นเทคโนโลยีที่น่าทึ่งมาก</textarea>
<label>🎭 Voice attributes</label>
<input type="text" id="instruct" placeholder="e.g. female, young adult, high pitch">
<div class="examples"><span class="example-tag" onclick="setInstruct('female, young adult, high pitch')">👧 สาวร่าเริง</span><span class="example-tag" onclick="setInstruct('male, middle-aged, low pitch')">👨‍💼 ทางการ</span><span class="example-tag" onclick="setInstruct('female, elderly, moderate pitch')">👩‍🦳 อ่อนโยน</span><span class="example-tag" onclick="setInstruct('male, whisper, british accent')">🤫 กระซิบ</span></div>
<div class="btn-row"><button class="btn-accent" onclick="generate('design')">🎨 Generate</button><button class="btn-outline" onclick="clearForm('design')">🔄 Clear</button></div>
</div></div>

<div class="tab-content" id="tab-auto">
<div class="card"><h2>🤖 Auto Voice Selection</h2>
<label>📝 Text to speak</label>
<textarea id="text-auto" placeholder="พิมพ์ข้อความ...">นี่คือการทดสอบการสังเคราะห์เสียงภาษาไทยด้วยระบบอัตโนมัติ โดยไม่ต้องใช้เสียงอ้างอิง</textarea>
<div class="btn-row"><button class="btn-outline" onclick="generate('auto')">🎲 Generate</button></div>
</div></div>

<div id="status" class="status"></div>
<div id="result" class="card" style="display:none"><h2>🔊 Result</h2><div class="audio-player"><audio id="audio-player" controls></audio></div><div class="history" id="history"></div></div>

<div class="card" style="margin-top:24px"><h2>📡 API Endpoints</h2>
<pre class="code">
POST /api/generate       — form-data: text, mode (clone|design|auto), ref_audio, ref_text, instruct
POST /api/generate/json  — JSON: {"text":"...", "mode":"auto", "ref_audio_b64":"..."}
GET  /api/health         — status + GPU info
</pre></div>
</div>

<script>
document.querySelectorAll('.tab').forEach(t=>{t.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));t.classList.add('active');document.getElementById('tab-'+t.dataset.tab).classList.add('active')})});
document.getElementById('ref-audio').addEventListener('change',function(){const i=document.getElementById('ref-info');if(this.files.length>0){const f=this.files[0];i.textContent=`✅ ${f.name} (${(f.size/1048576).toFixed(2)} MB)`;i.style.color='var(--green)'}else{i.textContent=''}});
function setExample(m,t){document.getElementById('text-'+m).value=t}
function setInstruct(t){document.getElementById('instruct').value=t}
function clearForm(m){document.getElementById('text-'+m).value='';if(m==='clone'){document.getElementById('ref-audio').value='';document.getElementById('ref-text').value='';document.getElementById('ref-info').textContent=''}if(m==='design')document.getElementById('instruct').value=''}
function setStatus(m,c){const e=document.getElementById('status');e.className='status '+c;e.textContent=m}
let hist=[];
async function generate(mode){const t=document.getElementById('text-'+mode).value.trim();if(!t){setStatus('⚠️ กรุณากรอกข้อความ','err');return}
const fd=new FormData();fd.append('text',t);fd.append('mode',mode);
if(mode==='clone'){const a=document.getElementById('ref-audio').files[0];const rt=document.getElementById('ref-text').value.trim();if(!a){setStatus('⚠️ กรุณาอัปโหลดไฟล์เสียงอ้างอิง','err');return}fd.append('ref_audio',a);if(rt)fd.append('ref_text',rt)}
if(mode==='design'){const ins=document.getElementById('instruct').value.trim();if(!ins){setStatus('⚠️ กรุณากรอกคำอธิบายเสียง','err');return}fd.append('instruct',ins)}
setStatus('⏳ กำลังสร้างเสียง...','info');
try{const r=await fetch('/api/generate',{method:'POST',body:fd});if(!r.ok){const e=await r.json();throw new Error(e.detail||r.statusText)}const b=await r.blob();const u=URL.createObjectURL(b);document.getElementById('audio-player').src=u;document.getElementById('result').style.display='block';setStatus('✅ เสร็จเรียบร้อย!','ok');
const ml={clone:'Voice Cloning',design:'Voice Design',auto:'Auto Voice'}[mode];const bc={clone:'clone',design:'design',auto:'auto'}[mode];
hist.unshift({url:u,mode:ml,bc,time:new Date().toLocaleTimeString('th-TH')});if(hist.length>5)hist.pop();
document.getElementById('history').innerHTML=hist.map(h=>`<div class="history-item"><span class="badge ${h.bc}">${h.mode}</span><span class="ts">${h.time}</span><audio controls src="${h.url}"></audio></div>`).join('')}catch(e){setStatus('❌ '+e.message,'err')}}
fetch('/api/health').then(r=>r.json()).then(d=>{if(d.model_loaded)setStatus('🟢 Model Ready — VRAM: '+d.vram_used_gb.toFixed(1)+' GB','ok');else setStatus('🟡 Loading...','info')}).catch(()=>setStatus('🔴 Cannot connect','err'));
</script>
</body></html>"""


# ── API Endpoints ───────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.get("/api/health")
async def health():
    gpu = {}
    if torch.cuda.is_available():
        gpu = {
            "device": DEVICE,
            "gpu_name": torch.cuda.get_device_name(0),
            "vram_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
            "vram_used_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
        }
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model_path": MODEL_PATH,
        "model_loading": _model_loading,
        "model_error": _model_error,
        **gpu,
    }


@app.post("/api/generate")
async def generate(
    text: str = Form(...),
    mode: str = Form(default="auto"),
    ref_audio: UploadFile | None = File(default=None),
    ref_text: str | None = Form(default=None),
    instruct: str | None = Form(default=None),
):
    """Generate TTS audio. Modes: clone (ref_audio), design (instruct), auto (none)."""
    if not text.strip():
        raise HTTPException(400, "text is required")
    if len(text) > 2000:
        raise HTTPException(400, "text too long (max 2000 chars)")

    model = get_model()
    tmpdir = None
    ref_path = None

    try:
        if ref_audio and ref_audio.filename:
            suffix = Path(ref_audio.filename).suffix or ".wav"
            tmpdir = tempfile.mkdtemp(prefix="omnivoice_")
            ref_path = os.path.join(tmpdir, f"ref{suffix}")
            with open(ref_path, "wb") as f:
                shutil.copyfileobj(ref_audio.file, f)

        kwargs = {"text": text.strip()}
        if mode == "clone" and ref_path:
            kwargs["ref_audio"] = ref_path
            if ref_text and ref_text.strip():
                kwargs["ref_text"] = ref_text.strip()
        elif mode == "design" and instruct:
            kwargs["instruct"] = validate_instruct(instruct.strip())

        print(f"[GEN] mode={mode}, text_len={len(text)}")

        with torch.inference_mode():
            audio = model.generate(**kwargs)

        oid = uuid.uuid4().hex[:10]
        op = OUTPUT_DIR / f"{oid}.wav"
        sf.write(str(op), audio[0], 24000)

        return FileResponse(op, media_type="audio/wav", filename=f"omnivoice_{oid}.wav", headers={"X-Output-ID": oid})

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Generation failed: {e}")
    finally:
        if tmpdir and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/api/generate/json")
async def generate_json(request: Request):
    """JSON-based generate. Returns base64 WAV."""
    import base64

    body = await request.json()
    text = body.get("text", "").strip()
    mode = body.get("mode", "auto")
    instruct = body.get("instruct", "").strip() or None
    ref_text = body.get("ref_text", "").strip() or None
    ref_audio_b64 = body.get("ref_audio_b64")

    if not text:
        raise HTTPException(400, "text is required")

    model = get_model()
    tmpdir = None
    ref_path = None

    try:
        if ref_audio_b64:
            tmpdir = tempfile.mkdtemp(prefix="omnivoice_")
            ref_path = os.path.join(tmpdir, "ref.wav")
            with open(ref_path, "wb") as f:
                f.write(base64.b64decode(ref_audio_b64))

        kwargs = {"text": text}
        if mode == "clone" and ref_path:
            kwargs["ref_audio"] = ref_path
            if ref_text:
                kwargs["ref_text"] = ref_text
        elif mode == "design" and instruct:
            kwargs["instruct"] = validate_instruct(instruct)

        with torch.inference_mode():
            audio = model.generate(**kwargs)

        buf = io.BytesIO()
        sf.write(buf, audio[0], 24000, format="WAV")
        buf.seek(0)
        return JSONResponse({
            "audio_b64": base64.b64encode(buf.read()).decode("utf-8"),
            "sample_rate": 24000,
            "duration_s": round(len(audio[0]) / 24000, 2),
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Generation failed: {e}")
    finally:
        if tmpdir and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── Main ────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("OMNIVOICE_PORT", "7860"))
    host = os.environ.get("OMNIVOICE_HOST", "0.0.0.0")
    print(f"[START] http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
