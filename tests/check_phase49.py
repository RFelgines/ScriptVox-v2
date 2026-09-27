"""check_phase49.py — rapport de nuit 2026-09-27 : profils de langue allemand et italien,
segment sans rien à prononcer.

Avant : « de » et « it » retombaient sur le profil français. Mesuré sur Gutenberg :
  - allemand (»…«) : le motif «[^»]*» du français partait du guillemet FERMANT d'une
    réplique jusqu'à l'OUVRANT de la suivante -> 128/128 « répliques » de Die
    Verwandlung étaient en fait de la narration ;
  - italien (tiret cadratin) : l'incise « — gridò Geppetto » restait collée à la
    réplique, lue avec la voix du personnage ;
  - EdgeTTS lisait l'allemand et l'italien avec des voix françaises.

Run: python tests/check_phase49.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="sv_p49_"))
os.environ.update({
    "LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3", "OLLAMA_CONTEXT_TOKENS": "8192",
    "DATABASE_URL": f"sqlite:///{_TMP}/p49.db", "HUEY_DB_PATH": f"{_TMP}/huey.db",
    "DATA_DIR": str(_TMP / "data"), "TTS_PROVIDER": "edgetts",
})
os.environ.pop("EDGETTS_VOICE_MAP", None)

_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    ok  {label}")
    else:
        msg = f"    FAIL  {label}" + (f" -- {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


def section(title: str) -> None:
    print(f"\n── {title}")


from app.config import Settings  # noqa: E402
from app.services.llm.base import _pre_segment  # noqa: E402
from app.services.llm.language_profiles import (  # noqa: E402
    DE_PROFILE, FR_PROFILE, IT_PROFILE, resolve_profile,
)
from app.services.tts import qwen as qwen_mod  # noqa: E402
from app.services.tts.edgetts import EdgeTTSProvider  # noqa: E402
from app.services.voice_assignment import VOICE_CATALOGUE  # noqa: E402


def _spans(text, profile):
    spans = _pre_segment(text, profile)
    check("découpe byte-exacte", "".join(s.text for s in spans) == text)
    return [s for s in spans if s.text.strip()]  # le « \n » final forme un span à part


# ── 1. resolve_profile ────────────────────────────────────────────────────────
section("resolve_profile : allemand et italien")
for val in ("de", "de-DE", "de-AT", "deu", "ger", "German", "Deutsch"):
    check(f"resolve_profile({val!r}) -> DE_PROFILE", resolve_profile(val) is DE_PROFILE)
for val in ("it", "it-IT", "ita", "Italian", "italiano"):
    check(f"resolve_profile({val!r}) -> IT_PROFILE", resolve_profile(val) is IT_PROFILE)


# ── 2. Allemand : »…« ─────────────────────────────────────────────────────────
section("DE_PROFILE : la narration entre deux répliques »…« reste de la narration")
de_text = ("»Was für ein stilles Leben die Familie doch führte,« sagte sich Gregor und "
           "fühlte Stolz. »Nun ist wieder alles stehengeblieben.«")
fr_spans = _pre_segment(de_text, FR_PROFILE)
check("témoin : le profil français inverse dialogue et narration",
      [s.text for s in fr_spans if s.is_dialogue] == ["« sagte sich Gregor und fühlte Stolz. »"],
      str([s.text for s in fr_spans if s.is_dialogue]))
de_spans = _spans(de_text, DE_PROFILE)
dialogues = [s.text for s in de_spans if s.is_dialogue]
check("2 répliques détectées, guillemets compris",
      dialogues == ["»Was für ein stilles Leben die Familie doch führte,«",
                    "»Nun ist wieder alles stehengeblieben.«"], str(dialogues))
check("l'incise « sagte sich Gregor » est narration",
      any(not s.is_dialogue and "sagte sich Gregor" in s.text for s in de_spans))

section("DE_PROFILE : guillemets bas-haut „…“ (édition moderne)")
de_mod = _spans("„Komm herein“, sagte der Vater. „Sofort!“", DE_PROFILE)
check("2 répliques „…“", [s.text for s in de_mod if s.is_dialogue] == ["„Komm herein“", "„Sofort!“"],
      str([s.text for s in de_mod if s.is_dialogue]))
check("pas d'incise_re (elle tombe déjà hors guillemets)", DE_PROFILE.incise_re is None)


# ── 3. Italien : tiret cadratin + incise ──────────────────────────────────────
section("IT_PROFILE : incise terminale séparée par un tiret")
it_spans = _spans("— Chetati, grillaccio del mal'augurio! — gridò Pinocchio.\n", IT_PROFILE)
check("réplique + incise", len(it_spans) == 2 and it_spans[0].is_dialogue and not it_spans[1].is_dialogue,
      str(it_spans))
check("la réplique garde son tiret final", it_spans[0].text.endswith("augurio! —"), repr(it_spans[0].text))
check("nom explicite -> Pinocchio", it_spans[0].incise_character == "Pinocchio", str(it_spans[0]))
check("témoin : le profil français ne scinde pas cette incise",
      len(_spans("— Chetati! — gridò Pinocchio.\n", FR_PROFILE)) == 1)

section("IT_PROFILE : sujet en minuscule précédé d'un article")
art = _spans("— Ma io il torsolo non lo mangio davvero!... — gridò il burattino rivoltandosi.\n",
             IT_PROFILE)
check("incise « gridò il burattino » séparée", len(art) == 2 and "gridò il burattino" in art[1].text,
      str(art))
check("« il burattino » n'est pas un nom propre -> pas d'attribution certaine",
      art[0].incise_character is None)
fata = _spans("— Non piangere più! — rispose la Fata.\n", IT_PROFILE)
check("« rispose la Fata » -> nom explicite", fata[0].incise_character == "la Fata", str(fata))

section("IT_PROFILE : clitique antéposé et incise suivie d'une virgule")
cli = _spans("— Vieni qui, — gli disse Geppetto.\n", IT_PROFILE)
check("« gli disse Geppetto » séparé", len(cli) == 2 and cli[0].incise_character == "Geppetto", str(cli))

section("IT_PROFILE : réplique reprise après l'incise -> intacte (dégradation bornée)")
rep_text = "— Sbucciarle? — replicò Geppetto meravigliato. — Non avrei mai creduto.\n"
rep = _spans(rep_text, IT_PROFILE)
check("un seul span dialogue", len(rep) == 1 and rep[0].is_dialogue, str(rep))

section("IT_PROFILE : pas de faux positif sans verbe d'incise")
nov = _spans("— Asino! — Polendina!\n", IT_PROFILE)
check("aucune scission", len(nov) == 1, str(nov))


# ── 4. Voix EdgeTTS ───────────────────────────────────────────────────────────
section("EdgeTTS : voix allemandes et italiennes")
_settings = Settings()
_ids = ["narrator"] + [v for ids in VOICE_CATALOGUE.values() for v in ids]
for lang, prefix in (("de", "de-"), ("it", "it-IT-")):
    p = EdgeTTSProvider(_settings, language=lang)
    entries = {vid: p._entry(vid) for vid in _ids}
    check(f"{lang} : tous les voice_id du catalogue résolus en {prefix}*",
          all(e[0].startswith(prefix) for e in entries.values()), str(entries))
    narr = entries["narrator"]
    check(f"{lang} : aucun personnage n'a la voix exacte du narrateur",
          all(e != narr for vid, e in entries.items() if vid != "narrator"))
    distinct = {e for vid, e in entries.items()}
    check(f"{lang} : les 9 emplacements sont tous distincts (voix, hauteur, débit)",
          len(distinct) == len(set(_ids)), f"{len(distinct)} / {len(set(_ids))}")


# ── 5. Qwen3-TTS ──────────────────────────────────────────────────────────────
section("Qwen3-TTS : langue transmise au modèle")
check("de -> German", qwen_mod._PROFILE_LANGUAGE[resolve_profile("de-DE").code] == "German")
check("it -> Italian", qwen_mod._PROFILE_LANGUAGE[resolve_profile("it").code] == "Italian")


# ── 6. Segment sans rien à prononcer ──────────────────────────────────────────
section("TTS : un segment sans lettre ni chiffre devient un silence (plus d'échec du chapitre)")
import asyncio  # noqa: E402

from app.services.audio import chapter as chapter_mod  # noqa: E402
from app.services.audio.format import silence_wav, wav_duration_ms  # noqa: E402
from app.services.tts.base import BaseTTSProvider  # noqa: E402


class _EdgeLike(BaseTTSProvider):
    """Se comporte comme EdgeTTS : échoue (NoAudioReceived) sur un texte imprononçable."""
    max_chars = 0

    def __init__(self):
        self.calls = []

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        self.calls.append(text)
        if not any(ch.isalnum() for ch in text):
            raise RuntimeError("No audio was received.")
        return silence_wav(400)


class _S:
    tts_max_chars = 0
    audio_normalize = True


_tts = _EdgeLike()
for txt in (")", "* * *", "…", " — ", "\n"):
    wav = asyncio.run(chapter_mod._synthesise_text(_tts, txt, "narrator", None, None, _S()))
    check(f"{txt!r} -> silence de 0 ms", wav_duration_ms(wav) == 0)
check("le moteur n'a jamais été appelé pour ces textes", _tts.calls == [], str(_tts.calls))
wav = asyncio.run(chapter_mod._synthesise_text(_tts, "Oui.", "narrator", None, None, _S()))
check("un vrai texte est toujours synthétisé", _tts.calls == ["Oui."] and wav_duration_ms(wav) == 400)
wav = asyncio.run(chapter_mod._synthesise_text(_tts, "Ω 42", "narrator", None, None, _S()))
check("chiffres et autres écritures comptent comme prononçables", _tts.calls[-1] == "Ω 42")


print()
if _errors:
    print(f"ÉCHEC : {len(_errors)} vérification(s)")
    sys.exit(1)
print("OK : toutes les vérifications passent")
