import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from TTS.api import TTS

os.environ.setdefault("COQUI_TOS_AGREED", "1")
MODEL_NAME = os.getenv("MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")
DEVICE_ENV = os.getenv("DEVICE", "auto").strip().lower()
PORT = int(os.getenv("PORT", "3199"))
TMP_DIR = Path(os.getenv("TMP_DIR", "/tmp/xtts-api"))
TMP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_SPEAKER_WAV = Path(
    os.getenv("DEFAULT_SPEAKER_WAV", str(Path(__file__).with_name("audio.wav")))
)

app = FastAPI(title="XTTS Voice Clone API", version="1.0.0")

_tts: Optional[TTS] = None
_device: Optional[str] = None


def resolve_device() -> str:
    if DEVICE_ENV in {"cpu", "cuda"}:
        if DEVICE_ENV == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return DEVICE_ENV
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_tts() -> TTS:
    global _tts, _device
    if _tts is None:
        _device = resolve_device()
        _tts = TTS(MODEL_NAME).to(_device)
    return _tts


def get_reference_wav(speaker_wav: Optional[UploadFile], workdir: Path) -> Path:
    if speaker_wav is None:
        if not DEFAULT_SPEAKER_WAV.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Audio de referencia padrao nao encontrado: {DEFAULT_SPEAKER_WAV}",
            )
        return DEFAULT_SPEAKER_WAV

    suffix = Path(speaker_wav.filename or "ref.wav").suffix or ".wav"
    reference_path = workdir / f"reference{suffix}"
    with reference_path.open("wb") as f:
        shutil.copyfileobj(speaker_wav.file, f)
    return reference_path


@app.on_event("startup")
def startup_event() -> None:
    get_tts()


@app.get("/")
def root() -> dict:
    return {
        "status": "ok",
        "service": "xtts-voice-clone-api",
        "model": MODEL_NAME,
        "device": _device or resolve_device(),
        "port": PORT,
        "default_speaker_wav": str(DEFAULT_SPEAKER_WAV),
        "endpoints": {
            "health": "/health",
            "tts": "/tts",
        },
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "loaded": _tts is not None,
        "model": MODEL_NAME,
        "device": _device or resolve_device(),
        "cuda_available": torch.cuda.is_available(),
        "default_speaker_wav_exists": DEFAULT_SPEAKER_WAV.exists(),
    }


@app.post("/tts")
async def generate_tts(
    text: str = Form(...),
    language: str = Form("pt"),
    speaker_wav: Optional[UploadFile] = File(None),
) -> FileResponse:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="O campo text nao pode ficar vazio.")

    workdir = Path(tempfile.mkdtemp(prefix="xtts_", dir=str(TMP_DIR)))
    output_path = workdir / "output.wav"

    try:
        reference_path = get_reference_wav(speaker_wav, workdir)

        tts = get_tts()
        tts.tts_to_file(
            text=cleaned_text,
            speaker_wav=str(reference_path),
            language=language,
            file_path=str(output_path),
        )

        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Falha ao gerar o audio.")

        return FileResponse(
            path=str(output_path),
            media_type="audio/wav",
            filename="output.wav",
            background=None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar audio: {exc}") from exc


@app.exception_handler(Exception)
async def generic_exception_handler(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})
