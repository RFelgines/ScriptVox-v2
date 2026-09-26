"""Provider TTS « programme externe » : branche n'importe quel moteur en ligne de commande.

Configuration (.env UNIQUEMENT — jamais modifiable par l'API, pour qu'aucune requête HTTP ne
puisse choisir la commande exécutée) :
  TTS_COMMAND            modèle de commande, ex.
      python C:/tts/run.py --in {text_file} --out {out} --voice {voice} --lang {language}
  TTS_COMMAND_TIMEOUT    secondes (300 par défaut)
  TTS_COMMAND_VOICE_MAP  JSON {"narrator": "nom_voix", ..., "default": "nom_voix"}

Marqueurs remplacés dans chaque argument : {text_file} (fichier UTF-8 contenant le texte),
{text} (le texte lui-même), {out} (fichier de sortie à écrire), {voice}, {emotion}, {ref}
(fichier audio de référence pour un clonage, sinon vide), {language} (« fr », « en »…).
Pas de shell : la commande est découpée puis lancée directement (aucune injection possible via
le texte du livre). Si la commande ne contient pas {out}, l'audio est lu sur sa sortie standard.
La sortie peut être WAV/MP3/FLAC/OGG, à toute fréquence : elle est normalisée.
"""
import asyncio
import os
import shlex
import tempfile
from pathlib import Path

from app.config import Settings
from app.core.exceptions import TTSError
from app.services.audio.format import normalize_audio
from app.services.llm.language_profiles import resolve_profile
from app.services.tts.base import BaseTTSProvider

_PLACEHOLDERS = ("{text_file}", "{text}", "{out}", "{voice}", "{emotion}", "{ref}", "{language}")


def _split_command(template: str) -> list[str]:
    """Découpe TTS_COMMAND en argv, sans shell.

    Sous Windows on ne peut pas utiliser le mode POSIX de shlex : il traite
    l'antislash comme un échappement et mange les séparateurs de chemin
    (``C:\\Tools\\tts.exe`` -> ``C:Toolstts.exe``). Mais le mode non-POSIX,
    lui, *conserve* les guillemets à l'intérieur du token : le premier argument
    devient littéralement ``"C:\\Program Files\\tts.exe"``, guillemets compris,
    et ``create_subprocess_exec`` — qui ne passe par aucun shell — cherche un
    exécutable portant ce nom, d'où un WinError 2. Un chemin cité étant la
    norme dès qu'il contient une espace, le moteur `command` était de fait
    inutilisable sous Windows. On retire donc les guillemets encadrants après
    coup, ce que le mode POSIX faisait déjà sur les autres plateformes.
    """
    if os.name != "nt":
        return shlex.split(template, posix=True)
    tokens = shlex.split(template, posix=False)
    unquoted = []
    for tok in tokens:
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ('"', "'"):
            tok = tok[1:-1]
        unquoted.append(tok)
    return unquoted


class CommandTTSProvider(BaseTTSProvider):
    max_chars = 800

    def __init__(self, settings: Settings, options: dict | None = None,
                 language: str | None = None) -> None:
        template = getattr(settings, "tts_command", None)
        if not template:
            raise TTSError("command:config", ValueError("TTS_COMMAND n'est pas défini (.env)."))
        self._argv_template = _split_command(template)
        self._timeout = float(getattr(settings, "tts_command_timeout", 300))
        voice_map = getattr(settings, "tts_command_voice_map", None)
        self._voice_map = voice_map if isinstance(voice_map, dict) else {}
        self._language = resolve_profile(language).code if language else ""

    def resolve_voice(self, voice_id: str) -> str:
        return str(self._voice_map.get(voice_id) or self._voice_map.get("default") or voice_id)

    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes:
        with tempfile.TemporaryDirectory(prefix="scriptvox_tts_") as tmp:
            text_file = Path(tmp) / "text.txt"
            out_file = Path(tmp) / "out.wav"
            text_file.write_text(text, encoding="utf-8")
            values = {
                "{text_file}": str(text_file), "{text}": text, "{out}": str(out_file),
                "{voice}": self.resolve_voice(voice_id), "{emotion}": emotion or "",
                "{ref}": reference_audio_path or "", "{language}": self._language,
            }
            argv = []
            for token in self._argv_template:
                for key, val in values.items():
                    token = token.replace(key, val)
                argv.append(token)
            uses_out = any("{out}" in t for t in self._argv_template)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), self._timeout)
            except asyncio.TimeoutError as exc:
                proc.kill()
                raise TTSError(f"command:{voice_id}", exc)
            except Exception as exc:
                raise TTSError(f"command:{voice_id}", exc)
            if proc.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace").strip()[-500:] or "<pas de stderr>"
                raise TTSError(
                    f"command:{voice_id}",
                    RuntimeError(f"code de sortie {proc.returncode} : {detail}"),
                )
            data = out_file.read_bytes() if uses_out and out_file.exists() else stdout
            if not data:
                raise TTSError(f"command:{voice_id}", RuntimeError("la commande n'a produit aucun audio"))
            try:
                return normalize_audio(data)
            except ValueError as exc:
                raise TTSError(f"command:{voice_id}", exc)
