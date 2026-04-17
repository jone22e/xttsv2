import logging
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
APP_DIR = Path(__file__).parent
MODEL_NAME = os.getenv("MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")
DEVICE_ENV = os.getenv("DEVICE", "auto").strip().lower()
PORT = int(os.getenv("PORT", "3199"))
TMP_DIR = Path(os.getenv("TMP_DIR", "/tmp/xtts-api"))
TMP_DIR.mkdir(parents=True, exist_ok=True)
MALE_SPEAKER_WAV = Path(
    os.getenv(
        "MALE_SPEAKER_WAV",
        os.getenv("DEFAULT_SPEAKER_WAV", str(APP_DIR / "audio.wav")),
    )
)
FEMALE_SPEAKER_WAV = Path(
    os.getenv("FEMALE_SPEAKER_WAV", str(APP_DIR / "feminina.wav"))
)
VOICE_REFERENCE_WAVS = {
    "m": MALE_SPEAKER_WAV,
    "f": FEMALE_SPEAKER_WAV,
}
PRELOAD_MODEL = os.getenv("PRELOAD_MODEL", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MIN_WAV_SIZE_BYTES = 44

logger = logging.getLogger("xtts-api")

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
        logger.info("Loading TTS model %s on %s", MODEL_NAME, _device)
        try:
            _tts = TTS(MODEL_NAME).to(_device)
        except SystemExit as exc:
            raise RuntimeError(
                f"Falha ao carregar modelo TTS: processo tentou sair com codigo {exc.code}"
            ) from exc
        logger.info("TTS model loaded on %s", _device)
    return _tts


def get_reference_wav(
    speaker_wav: Optional[UploadFile],
    workdir: Path,
    voz: str,
) -> Path:
    if speaker_wav is None:
        selected_voice = (voz or "m").strip().lower()
        reference_wav = VOICE_REFERENCE_WAVS.get(selected_voice)
        if reference_wav is None:
            raise HTTPException(
                status_code=400,
                detail="O campo voz deve ser 'm' ou 'f'.",
            )
        if not reference_wav.exists():
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Audio de referencia para voz '{selected_voice}' "
                    f"nao encontrado: {reference_wav}"
                ),
            )
        return reference_wav

    suffix = Path(speaker_wav.filename or "ref.wav").suffix or ".wav"
    reference_path = workdir / f"reference{suffix}"
    with reference_path.open("wb") as f:
        shutil.copyfileobj(speaker_wav.file, f)
    return reference_path


def validate_output_wav(output_path: Path) -> None:
    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Falha ao gerar o audio.")

    output_size = output_path.stat().st_size
    if output_size <= MIN_WAV_SIZE_BYTES:
        raise HTTPException(
            status_code=500,
            detail=f"Audio gerado vazio ou incompleto ({output_size} bytes).",
        )

    with output_path.open("rb") as output_file:
        header = output_file.read(12)

    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise HTTPException(
            status_code=500,
            detail="Audio gerado nao tem cabecalho WAV valido.",
        )


@app.on_event("startup")
def startup_event() -> None:
    logger.info(
        "Starting XTTS API with voice references %s",
        {
            voice: {"path": str(path), "exists": path.exists()}
            for voice, path in VOICE_REFERENCE_WAVS.items()
        },
    )
    if PRELOAD_MODEL:
        get_tts()


@app.get("/")
def root() -> dict:
    return {
        "status": "ok",
        "service": "xtts-voice-clone-api",
        "model": MODEL_NAME,
        "device": _device or resolve_device(),
        "port": PORT,
        "voice_reference_wavs": {
            voice: str(path) for voice, path in VOICE_REFERENCE_WAVS.items()
        },
        "preload_model": PRELOAD_MODEL,
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
        "voice_reference_wavs": {
            voice: {"path": str(path), "exists": path.exists()}
            for voice, path in VOICE_REFERENCE_WAVS.items()
        },
        "preload_model": PRELOAD_MODEL,
    }


@app.post("/tts")
async def generate_tts(
    text: str = Form(...),
    language: str = Form("pt"),
    voz: str = Form("m"),
    speaker_wav: Optional[UploadFile] = File(None),
) -> FileResponse:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="O campo text nao pode ficar vazio.")

    workdir = Path(tempfile.mkdtemp(prefix="xtts_", dir=str(TMP_DIR)))
    output_path = workdir / "output.wav"

    try:
        reference_path = get_reference_wav(speaker_wav, workdir, voz)

        tts = get_tts()
        tts.tts_to_file(
            text=cleaned_text,
            speaker_wav=str(reference_path),
            language=language,
            file_path=str(output_path),
        )

        validate_output_wav(output_path)

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
