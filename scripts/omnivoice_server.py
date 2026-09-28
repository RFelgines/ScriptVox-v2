"""Serveur local OmniVoice (k2-fsa) pour ScriptVox — moteur TTS `omnivoice`.

Pourquoi un processus séparé : OmniVoice exige transformers>=5.3, alors que Qwen3-TTS
(qwen-tts) reste en transformers 4.x. Les deux ne cohabitent pas dans un même
environnement. Ce serveur tourne dans son propre venv (.venv-omni) et garde le modèle
chargé ; l'API et le worker ScriptVox lui parlent en HTTP (app/services/tts/omnivoice.py).

LICENCE : le code d'OmniVoice est sous Apache-2.0, mais les POIDS du modèle sont sous
CC-BY-NC (données d'entraînement Emilia) — usage NON COMMERCIAL uniquement.

Installation (Windows, AMD ROCm — même recette que .venv-rocm) :
    py -3.12 -m venv .venv-omni
    R=https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1
    .venv-omni\\Scripts\\pip install $R/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl \\
        $R/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl \\
        $R/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl $R/rocm-7.2.1.tar.gz
    .venv-omni\\Scripts\\pip install "$R/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl" \\
        "$R/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
    .venv-omni\\Scripts\\pip install omnivoice==0.2.1 num2words
(NVIDIA : torch CUDA à la place des deux étapes ROCm.)

Lancement :  .venv-omni\\Scripts\\python scripts\\omnivoice_server.py  [--port 8770]
N'écoute que sur 127.0.0.1 : aucun accès réseau extérieur.

Mesures sur Radeon RX 9070 XT (ROCm 7.2.1, fp16, MIOPEN_FIND_MODE=FAST, après échauffement) :
32 étapes RTF 0,18 ; 16 étapes 0,074 ; 8 étapes 0,040 ; 4 phrases en lot à 16 étapes 0,028.
Sans MIOPEN_FIND_MODE=FAST, MIOpen recherche ses noyaux à chaque nouvelle forme de tenseur
et la synthèse tombe à RTF ~1,7 : ce serveur le positionne donc avant d'importer torch.

API :
  GET  /health       -> {"ok": true, "device": ..., "model": ...}
  POST /synthesize   JSON -> audio/wav (24 kHz mono 16 bits)
       text (obligatoire), language, num_step, speed,
       ref_audio_path [+ ref_text]  -> clonage (mode le plus stable, voix constante) ;
       instruct                      -> voix conçue (« female, elderly, low pitch »).
       Une voix conçue est générée UNE fois (échantillon de référence, graine fixe) puis
       CLONÉE pour chaque appel suivant : la même description donne la même voix d'un bout
       à l'autre du livre, ce que la conception directe ne garantit pas.
  POST /design       JSON {instruct, text, language?, out_path} -> écrit l'échantillon de
       référence d'une voix conçue (et sa transcription .txt) ; sert à créer la voix d'un
       personnage dans ScriptVox.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import threading
from pathlib import Path

os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")  # avant l'import de torch (voir docstring)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

SAMPLE_RATE = 24000
DEFAULT_STEPS = int(os.environ.get("OMNIVOICE_NUM_STEP", "32"))
# Phrases neutres pour fabriquer l'échantillon de référence d'une voix conçue.
_DESIGN_TEXT = {
    "fr": "Le soir tombait doucement sur la ville, et chacun rentrait chez soi sans se presser.",
    "en": "Evening was slowly falling over the town, and everyone was walking home unhurried.",
    "es": "La tarde caía despacio sobre la ciudad, y cada uno volvía a casa sin prisa.",
    "de": "Der Abend senkte sich langsam über die Stadt, und jeder ging gemächlich nach Hause.",
    "it": "La sera scendeva piano sulla città, e ognuno tornava a casa senza fretta.",
}

app = FastAPI(title="OmniVoice pour ScriptVox")
_lock = threading.Lock()  # un seul appel GPU à la fois
_state: dict = {"model": None}
_prompts: dict[str, object] = {}  # clé -> VoiceClonePrompt (clonage mis en cache)


def _model():
    if _state["model"] is None:
        from omnivoice import OmniVoice
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device != "cpu" else torch.float32
        _state["model"] = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device, dtype=dtype)
        _state["device"] = torch.cuda.get_device_name(0) if device != "cpu" else "cpu"
    return _state["model"]


def _config(num_step: int | None):
    from omnivoice.models.omnivoice import OmniVoiceGenerationConfig
    return OmniVoiceGenerationConfig(num_step=num_step or DEFAULT_STEPS)


def _wav_bytes(samples) -> bytes:
    a = np.asarray(samples, dtype=np.float32).squeeze()
    buf = io.BytesIO()
    sf.write(buf, a, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _clone_prompt(ref_audio_path: str, ref_text: str | None):
    key = f"{ref_audio_path}|{os.path.getmtime(ref_audio_path)}|{ref_text or ''}"
    if key not in _prompts:
        kw = {"ref_audio": ref_audio_path}
        if ref_text:
            kw["ref_text"] = ref_text
        _prompts[key] = _model().create_voice_clone_prompt(**kw)
    return _prompts[key]


def _design_reference(instruct: str, language: str | None) -> tuple[bytes, str]:
    """Échantillon de référence d'une voix conçue, reproductible (graine dérivée de la
    description et de la langue)."""
    text = _DESIGN_TEXT.get((language or "fr")[:2], _DESIGN_TEXT["fr"])
    seed = int(hashlib.sha1(f"{instruct}|{language}".encode()).hexdigest()[:8], 16)
    torch.manual_seed(seed)
    audio = _model().generate(text=text, instruct=instruct, language=language,
                              generation_config=_config(32))
    return _wav_bytes(audio[0]), text


def _designed_prompt(instruct: str, language: str | None):
    key = f"design|{instruct}|{language}"
    if key not in _prompts:
        wav, text = _design_reference(instruct, language)
        cache = Path(os.environ.get("OMNIVOICE_CACHE", Path.home() / ".cache" / "scriptvox-omnivoice"))
        cache.mkdir(parents=True, exist_ok=True)
        ref = cache / f"design_{hashlib.sha1(key.encode()).hexdigest()[:12]}.wav"
        ref.write_bytes(wav)
        _prompts[key] = _model().create_voice_clone_prompt(ref_audio=str(ref), ref_text=text)
    return _prompts[key]


class SynthIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = None
    instruct: str | None = None
    ref_audio_path: str | None = None
    ref_text: str | None = None
    num_step: int | None = Field(default=None, ge=4, le=64)
    speed: float | None = Field(default=None, gt=0.3, lt=3.0)


class DesignIn(BaseModel):
    instruct: str = Field(min_length=1, max_length=300)
    language: str | None = None
    out_path: str


@app.get("/health")
def health() -> dict:
    _model()
    return {"ok": True, "device": _state.get("device"), "model": "k2-fsa/OmniVoice",
            "num_step": DEFAULT_STEPS, "miopen_find_mode": os.environ.get("MIOPEN_FIND_MODE")}


@app.post("/synthesize")
def synthesize(body: SynthIn) -> Response:
    with _lock:
        try:
            kw = {"text": body.text, "language": body.language,
                  "generation_config": _config(body.num_step)}
            if body.speed:
                kw["speed"] = body.speed
            if body.ref_audio_path:
                if not Path(body.ref_audio_path).is_file():
                    raise HTTPException(status_code=404, detail=f"ref_audio_path not found: {body.ref_audio_path}")
                kw["voice_clone_prompt"] = _clone_prompt(body.ref_audio_path, body.ref_text)
            elif body.instruct:
                kw["voice_clone_prompt"] = _designed_prompt(body.instruct, body.language)
            audio = _model().generate(**kw)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    return Response(content=_wav_bytes(audio[0]), media_type="audio/wav")


@app.post("/design")
def design(body: DesignIn) -> dict:
    with _lock:
        try:
            wav, text = _design_reference(body.instruct, body.language)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    out = Path(body.out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav)
    out.with_suffix(".txt").write_text(text, encoding="utf-8")
    return {"path": str(out), "reference_text": text}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("OMNIVOICE_PORT", "8770")))
    args = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
